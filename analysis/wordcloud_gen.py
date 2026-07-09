"""
词云生成模块 — 从 51job 职位标签（keywords / jobTags）中统计高频热词。

- 只从 keywords（51job jobTags）提取，这是平台官方标注的结构化标签（技能/福利/经验/学历等），已按空格分隔为完整标签
- 严格按 keywords 原样统计（高频热词板块，不局限于技能词），仅做同义词归一化（js->JavaScript 等）与最小清洗
- 不套用为职位描述(content)设计的 STOP_WORDS，避免误杀 java/c++/ai/计算机 等真实标签
- echarts-wordcloud 前端圆形布局渲染（maskImage 中国地图轮廓已由 ensure_china_mask 生成，但未启用）
- mask 图片自动从 GeoJSON 生成（首次运行时）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from collections import Counter

_logger = logging.getLogger('job_analysis')


# ========== 技术词同义词归一化 ==========
TERM_NORMALIZE = {
    'css3': 'CSS', 'css': 'CSS', 'scss': 'CSS', 'sass': 'CSS',
    'javascript': 'JavaScript', 'js': 'JavaScript', 'ecmascript': 'JavaScript',
    'typescript': 'TypeScript', 'ts': 'TypeScript',
    'vue': 'Vue', 'vuejs': 'Vue', 'vue2': 'Vue', 'vue3': 'Vue',
    'react': 'React', 'reactjs': 'React', 'react.js': 'React',
    'angular': 'Angular', 'angularjs': 'Angular',
    'html': 'HTML', 'html5': 'HTML',
    'web': 'Web', 'webpack': 'Webpack',
    'node': 'Node.js', 'nodejs': 'Node.js', 'node.js': 'Node.js',
    'python': 'Python', 'java': 'Java', 'golang': 'Go', 'go': 'Go',
    'c#': 'C#', 'c++': 'C++', 'c': 'C', 'rust': 'Rust',
    'php': 'PHP', 'ruby': 'Ruby', 'swift': 'Swift', 'kotlin': 'Kotlin',
    'spring': 'Spring', 'springboot': 'SpringBoot', 'springmvc': 'Spring MVC',
    'springcloud': 'SpringCloud', 'mybatis': 'MyBatis',
    'django': 'Django', 'flask': 'Flask', 'fastapi': 'FastAPI',
    'mysql': 'MySQL', 'postgresql': 'PostgreSQL', 'mongodb': 'MongoDB',
    'redis': 'Redis', 'elasticsearch': 'Elasticsearch',
    'oracle': 'Oracle', 'sqlite': 'SQLite',
    'docker': 'Docker', 'kubernetes': 'Kubernetes', 'k8s': 'Kubernetes',
    'jenkins': 'Jenkins', 'gitlab': 'GitLab', 'git': 'Git',
    'nginx': 'Nginx', 'tomcat': 'Tomcat', 'linux': 'Linux', 'unix': 'Unix',
    'aws': 'AWS', 'azure': 'Azure',
    'tensorflow': 'TensorFlow', 'pytorch': 'PyTorch',
    'opencv': 'OpenCV', 'pandas': 'Pandas', 'numpy': 'NumPy',
    'hadoop': 'Hadoop', 'spark': 'Spark', 'kafka': 'Kafka',
    'flink': 'Flink', 'hive': 'Hive',
    'tcp': 'TCP', 'http': 'HTTP', 'https': 'HTTPS', 'api': 'API',
    'restful': 'RESTful', 'rest': 'REST',
    'json': 'JSON', 'xml': 'XML', 'yaml': 'YAML',
    'mq': 'MQ', 'rabbitmq': 'RabbitMQ',
    'memcached': 'Memcached', 'memcache': 'Memcached',
    'maven': 'Maven', 'gradle': 'Gradle', 'npm': 'NPM', 'yarn': 'Yarn',
    'es6': 'ES6', 'es7': 'ES7',
    'scikit': 'scikit-learn', 'sklearn': 'scikit-learn',
    'matlab': 'MATLAB', 'labview': 'LabVIEW',
    'solidworks': 'SolidWorks', 'autocad': 'AutoCAD', 'cad': 'CAD',
    'plc': 'PLC', 'stm32': 'STM32', 'arm': 'ARM', 'fpga': 'FPGA',
    'ros': 'ROS', 'slam': 'SLAM',
    '大模型': 'LLM', 'llm': 'LLM', 'langchain': 'LangChain',
    'ai': 'AI', '人工智能': 'AI',
    'sql': 'SQL', 'it': 'IT',
    '安卓': 'Android', 'android': 'Android',
    'oa': 'OA', 'mes': 'MES', 'plm': 'PLM', 'erp': 'ERP',
    'jquery': 'jQuery', 'jqueryui': 'jQuery UI',
    'bootstrap': 'Bootstrap',
    'hibernate': 'Hibernate', 'struts': 'Struts',
    '微服务': '微服务', '微服务架构': '微服务',
    '全栈': '全栈',
    'devops': 'DevOps', 'cicd': 'CI/CD',
    'prometheus': 'Prometheus', 'grafana': 'Grafana',
    'vuex': 'Vuex', 'pinia': 'Pinia',
    'redux': 'Redux', 'mobx': 'Mobx',
    'sass': 'Sass',
    'less': 'Less',
    'webgl': 'WebGL',
    '小程序': '小程序',
    'uniapp': 'UniApp', 'uni-app': 'UniApp',
}


# ========== 停用词（仅从职位标题中提取，过滤远少于 content 场景） ==========
STOP_WORDS = {
    # 职位后缀/级别
    '工程师', '高级', '中级', '初级', '资深', '实习', '助理',
    '主管', '经理', '总监', '架构师', '专家', '顾问',
    '开发', '技术', '岗位', '方向', '相关',
    # 学历
    '本科', '大专', '硕士', '博士', '中专', '高中', '学历', '学位',
    '本科及以上', '大专及以上', '统招', '全日制', '及以上',
    # 城市/地区名
    '北京', '上海', '广州', '深圳', '杭州', '南京', '苏州',
    '成都', '武汉', '西安', '重庆', '天津', '长沙', '合肥',
    '厦门', '福州', '郑州', '济南', '青岛', '大连', '沈阳',
    '无锡', '宁波', '东莞', '珠海', '佛山',
    '朝阳', '海淀', '浦东', '天河', '南山', '福田', '宝安',
    # 公司后缀
    '科技', '信息', '集团', '有限', '公司',
    # 招聘无意义词
    '职位', '描述', '要求', '工作', '负责', '提供', '福利', '待遇',
    '薪资', '面议', '全职', '学历', '经验',
    '行业', '技术员', '出差', '办公', '环境', '交通', '便利',
    '团队', '氛围', '培训', '晋升', '优秀', '良好', '具备',
    # 福利/补贴（含拆分碎片）
    '五险', '一金', '五险一金', '补贴', '带薪', '年假', '奖金', '年终', '绩效',
    '年终奖金', '绩效奖金', '补充', '公积金', '商业', '保险',
    '定期', '体检', '专业培训', '员工', '旅游', '周末', '双休',
    '餐补', '房补', '交通补贴', '通讯补贴', '节日', '生日',
    '弹性', '股票', '期权', '零食', '下午茶', '年度', '调薪',
    '六险', '二金', '三金', '包吃', '包住', '免费', '班车',
    '做五休', '做五休二', '做六休', '做六休一', '大小周', '单休',
    '病假', '事假', '婚假', '产假', '陪产假', '丧假', '探亲假', '公假',
    '全勤', '全勤奖', '工龄', '工龄奖', '项目奖金', '季度',
    '有餐', '有餐补', '有住', '话补', '高温', '高温补贴',
    '无需', '经验不限', '无需经验', '接受', '应届',
    '节假日', '法定', '假期', '劳动', '社保', '合同', '签订',
    '医疗', '养老', '失业', '工伤', '生育', '缴纳',
    '住房', '住房补贴', '午餐', '晚餐', '完善', '丰厚',
    '保障', '按照国家', '规定', '享受', '标准', '国家',
    '出国', '机会', '外派', '驻外',
    # 连接词/助词
    '的', '和', '及', '与', '等', '有', '在', '为', '或', '是',
    '了', '不', '可', '能', '会', '要', '将', '对', '从', '到',
    # 通用动词/形容词
    '熟悉', '能力', '了解', '优先', '使用', '熟练', '基础', '学习',
    '具有', '专业', '扎实', '精通', '掌握', '善于', '至少',
    '一种', '以上学历', '以上', '以下', '不限', '应届', '若干',
    '能够', '独立', '完成', '编写', '进行', '实现', '参与', '推动',
    '提升', '优化', '维护', '管理', '理解', '深入', '热爱',
    '精神', '项目', '熟练掌握',
    # 年限
    '1-3', '3-5', '5-10', '一年', '三年', '五年', '二年', '四年',
    # 单字
    '的', '了', '在', '是', '我', '有', '和', '就', '不', '人',
    '都', '一', '个', '上', '也', '很', '到', '说', '要', '去',
    '你', '会', '着', '没有', '看', '好', '自己', '这',
    # 数字相关
    '大', '中', '小', '高', '低', '强', '弱', '新', '旧',
    # 太泛的技术/行业词
    '数据库', '计算机', '软件', '互联网', '通信', '网络', '通讯',
    '系统', '平台', '服务', '产品', '需求', '分析', '方案',
    '问题', '解决', '支持', '协助', '代码', '编程', '研发',
    '设计', '应用', '框架', '配置', '集成',
    # 通用碎片
    '提供', '说明', '针对', '包括', '其中', '具体', '根据',
    '处理', '业务', '客户', '销售', '市场', '运营',
    '测试',  # "测试工程师" → 拆分后单留"测试"，太泛（留给"软件测试"等归一化处理）
    '语言', '单元', '模块', '组件',
    # 碎片
    '餐饮', '酒店', '医学', '教育', '金融', '物流', '能源',
    '医疗保险', '养老保险', '失业保险', '工伤保险', '生育保险',
    '加班', '补助', '住房', '公积', '住房补贴',
    '节日', '福利', '生日', '补贴', '话补', '食补', '住补',
    '包吃', '包住', '免费', '班车', '团建',
    '环境', '氛围', '周末', '双休', '单休',
    '专业', '培训', '晋升', '渠道', '空间', '前景',
    '周末', '节日', '下午茶', '零食',
    '高温', '补贴', '补充', '商业', '保险',
    '公积金', '社保', '缴纳', '基数',
    # 太泛的开发/技术方向词
    '软件开发', '软件工程', '信息技术', '信息', '数据',
    '架构', '设计', '开发', '研发', '编程', '代码',
    # 语言/非技能
    '粤语', '英语', '日语', '韩语', '普通话', '汉语',
    # 公司/业务类
    '企业', '公司', '集团', '有限', '科技',
    '交易', '赋能', '资本', '现场', '面试',
    '二次开发', '中证',
    # 等级/级别
    '中高级', '初中高', '中级', '高级',
    # 国名/地名（标题中偶尔出现）
    '中国', '美国', '日本', '韩国', '新加坡',
    # 太泛的通用词
    '实习生', '智能', '人工智能',
    '程序员', '应届生', '招聘', '广告', '制造', '海外', '总部', '国企', '创新',
    # 碎片词
    '联网', '运通',
    # 非技术动词/名词/公司名
    '阿里', '优稳', '高新', '客服', '骑行', '大唐',
    '实施', '仪器', '一金交', '一轮', '模型',
    # 数字ID碎片（标题有时含职位编号）
    'j10064', 'j20877', 'j13203',
    # 噪音词（jieba 分词碎片）
    'mom', '短信', '基金项目', '基金', '青浦区', '地理位置', '上交所',
    '地面', '系统软件', '中建', '前后', '网关', '需要', '客户端',
    '数字化', '实时', '中转', '互联', '高频', 'evb', '底层', '国际化',
    'leader', '程序', '证券', '驻场', '服务端', '产品', '投研', '路网',
    '央企', 'aiops', '工程', '应用软件', '制造业', '必须', '中间件',
    '车手', '背景', '社招', '工业', 'plm', 'android', '前后端',
    'c++', 'java', 'python', 'ai', 'oa', 'mes', 'erp', 'vue',
    'devops', '前后端', '后端运维',
    '双语', '地理位置', '地面', '需要', '前后', '实时',
    '中转', '底层', '国际化', '服务端', '产品', '投研',
    '应用软件', '必须', '车手', '背景',
}

# 白名单：这些词不受停用词影响（技术含义强）
WHITELIST = {
    'Python', 'Java', 'Go', 'C++', 'C', 'C#', 'Rust', 'PHP', 'Ruby',
    'Swift', 'Kotlin', 'Scala', 'R', 'Perl', 'Lua', 'Dart', 'Haskell',
    'MATLAB',
    'JavaScript', 'TypeScript', 'HTML', 'CSS', 'SQL', 'JSON', 'XML',
    'Vue', 'React', 'Angular', 'Svelte',
    'Spring', 'Django', 'Flask', 'FastAPI', 'Express',
    'MySQL', 'PostgreSQL', 'MongoDB', 'Redis', 'Oracle', 'SQLite',
    'Docker', 'Kubernetes', 'Jenkins', 'Nginx', 'Tomcat', 'Linux',
    'Git', 'GitLab', 'GitHub',
    'AWS', 'Azure',
    'TensorFlow', 'PyTorch', 'OpenCV', 'Pandas', 'NumPy',
    'LLM', 'LangChain', 'AI', '深度学习', '机器学习',
    '微服务', '分布式', '高并发', '全栈',
}


def _connect_db():
    """获取数据库连接"""
    import sqlite3
    from config import DB_PATH
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def ensure_china_mask(mask_path=None):
    """
    确保中国地图 mask 图片存在。不存在时从 GeoJSON 自动生成。

    mask 格式: RGBA PNG，中国地图区域为白色+透明(alpha=0)，
    背景为黑色+不透明(alpha=255)。这样无论 wordcloud2 看 alpha
    还是亮度，文字都会填充在地图形状内。

    返回:
        str: mask 图片路径，失败返回 None
    """
    if mask_path is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        mask_path = os.path.join(base, 'static', 'china_mask.png')

    if os.path.exists(mask_path):
        return mask_path

    geojson_path = os.path.join(os.path.dirname(mask_path), 'china_geo.json')
    if not os.path.exists(geojson_path):
        _logger.warning('china_geo.json 不存在，无法生成 mask')
        return None

    try:
        import json
        from PIL import Image, ImageDraw

        with open(geojson_path, 'r', encoding='utf-8') as f:
            geo = json.load(f)

        all_lons, all_lats = [], []
        polygons = []   # [(外环点列, [内环点列, ...]), ...]

        for feat in geo.get('features', []):
            geom = feat.get('geometry')
            if not geom:
                continue
            gtype = geom.get('type')
            coords = geom.get('coordinates', [])
            if not coords:
                continue

            if gtype == 'Polygon':
                # 第一个 ring 是外环，其余是内环(洞)
                poly_rings = []
                for ring in coords:
                    pts = [(p[0], p[1]) for p in ring if len(p) >= 2]
                    if len(pts) >= 3:
                        poly_rings.append(pts)
                if poly_rings:
                    polygons.append(poly_rings)
                    for ring in poly_rings:
                        for p in ring:
                            all_lons.append(p[0])
                            all_lats.append(p[1])

            elif gtype == 'MultiPolygon':
                for poly in coords:
                    poly_rings = []
                    for ring in poly:
                        pts = [(p[0], p[1]) for p in ring if len(p) >= 2]
                        if len(pts) >= 3:
                            poly_rings.append(pts)
                    if poly_rings:
                        polygons.append(poly_rings)
                        for ring in poly_rings:
                            for p in ring:
                                all_lons.append(p[0])
                                all_lats.append(p[1])

        if not polygons:
            _logger.warning('GeoJSON 中无有效多边形')
            return None

        # 画布尺寸 — 与中国地图经纬度比例匹配，避免拉伸
        W, H = 1200, 900
        pad = 20

        min_lon, max_lon = min(all_lons), max(all_lons)
        min_lat, max_lat = min(all_lats), max(all_lats)

        lon_scale = (W - 2 * pad) / (max_lon - min_lon)
        lat_scale = (H - 2 * pad) / (max_lat - min_lat)
        # 保持等比例，取较小缩放因子
        scale = min(lon_scale, lat_scale)

        # 计算居中偏移
        data_w = (max_lon - min_lon) * scale
        data_h = (max_lat - min_lat) * scale
        off_x = (W - data_w) / 2
        off_y = (H - data_h) / 2

        def _proj(lon, lat):
            x = off_x + (lon - min_lon) * scale
            # 纬度北高南低，图片 y 轴南高北低，需要翻转
            y = H - (off_y + (lat - min_lat) * scale)
            return x, y

        # 创建 RGBA 图片: 背景黑色+不透明, 地图白色+透明
        img = Image.new('RGBA', (W, H), (0, 0, 0, 255))
        draw = ImageDraw.Draw(img)

        for poly_rings in polygons:
            if not poly_rings:
                continue
            outer = [_proj(p[0], p[1]) for p in poly_rings[0]]
            # PIL ImageDraw.polygon 不支持带洞的多边形，
            # 这里只画外环（中国省界密集，忽略湖泊/洞对整体轮廓影响极小）
            if len(outer) >= 3:
                # 白色 + alpha=0（透明，表示可放文字的区域）
                draw.polygon(outer, fill=(255, 255, 255, 0))

        os.makedirs(os.path.dirname(mask_path), exist_ok=True)
        img.save(mask_path, 'PNG')
        _logger.info(f'中国地图 mask 已生成: {mask_path} ({W}x{H})')
        return mask_path

    except Exception as e:
        _logger.warning(f'生成中国地图 mask 失败: {e}')
        return None


def generate_wordcloud_data(top_n=60):
    """
    仅从数据库 keywords（51job jobTags）中提取标签，严格按原样统计高频热词。

    - keywords：来自 51job 的职位标签(jobTags)，直接按空格拆分，
      严格按平台原始标签统计（高频热词板块，含技能/福利/经验/学历等全部标签）。
    - 不使用 post 或 content，避免职位描述长文本分词噪音；jobTags 已是结构化标签。
    - 仅做同义词归一化（js->JavaScript, c++->C++, ai->AI ...），不再套用 STOP_WORDS，
      以免误杀 java/c++/ai/计算机 等真实出现的标签。

    返回:
        dict: {
            'success': bool,
            'total_jobs': int,
            'words': [(word, count), ...],
        }
    """
    try:
        db = _connect_db()
        cursor = db.cursor()
        cursor.execute("SELECT keywords FROM data")
        rows = cursor.fetchall()
        db.close()
    except Exception as e:
        _logger.error("词云数据查询失败: %s", e)
        return {'success': False, 'total_jobs': 0, 'words': [], 'error': str(e)}

    if not rows:
        return {'success': True, 'total_jobs': 0, 'words': []}

    # keywords 是 51job 平台官方标注的结构化标签(jobTags), 已按空格分隔为完整标签,
    # 不存在长文本分词噪音. 因此严格按原样统计(高频热词含技能/福利/经验/学历等全部标签),
    # 仅做同义词归一化(js->JavaScript, c++->C++, ai->AI ...)与最小清洗,
    # 不套用为职位描述(content)设计的 STOP_WORDS, 避免误杀 java/c++/ai 等真实标签.
    counter = Counter()
    for r in rows:
        kw_str = (r[0] or '').strip()
        if not kw_str:
            continue
        for w in kw_str.split():
            w = w.strip()
            if len(w) < 2 or w.isdigit():
                continue
            # 同义词归一化: js->JavaScript, java->Java, c++->C++, ai->AI 等
            w = TERM_NORMALIZE.get(w, w)
            counter[w] += 1

    top_words = counter.most_common(top_n)
    return {
        'success': True,
        'total_jobs': len(rows),
        'words': top_words,
    }



# ---------- 命令行测试 ----------
if __name__ == '__main__':
    ensure_china_mask()
    data = generate_wordcloud_data(top_n=30)
    print(f"总职位数: {data['total_jobs']}")
    print(f"Top 30 关键词:")
    for w, c in data['words']:
        print(f"  {w:20s} {c}")
