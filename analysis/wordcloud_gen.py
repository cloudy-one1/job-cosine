"""
词云生成模块 — 从职位标题中提取高频技术关键词。

- 只从 post（职位标题）提取，避免 content（描述）中的福利/招聘噪音
- 使用 echarts-wordcloud + maskImage 前端渲染中国地图形状
- 停用词覆盖福利、学历、城市、招聘用语等
- mask 图片自动从 GeoJSON 生成（首次运行时）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
import logging
from collections import Counter

import jieba

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

    返回:
        str: mask 图片路径，失败返回 None
    """
    if mask_path is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        mask_path = os.path.join(base, 'static', 'china_mask.png')

    if os.path.exists(mask_path):
        return mask_path

    # 尝试从 GeoJSON 生成
    geojson_path = os.path.join(os.path.dirname(mask_path), 'china_geo.json')
    if not os.path.exists(geojson_path):
        _logger.warning('china_geo.json 不存在，无法生成 mask，将跳过中国地图形状')
        return None

    try:
        import json
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon

        with open(geojson_path, 'r', encoding='utf-8') as f:
            geo = json.load(f)

        patches = []
        all_lons, all_lats = [], []

        for feat in geo.get('features', []):
            geom = feat.get('geometry')
            if not geom:
                continue
            gtype = geom.get('type')
            coords = geom.get('coordinates', [])
            if not coords:
                continue

            def _extract_rings(c):
                rings = []
                if gtype == 'Polygon':
                    for ring in c:
                        pts = [(p[0], p[1]) for p in ring if len(p) >= 2]
                        if len(pts) >= 3:
                            rings.append(pts)
                elif gtype == 'MultiPolygon':
                    for poly in c:
                        for ring in poly:
                            pts = [(p[0], p[1]) for p in ring if len(p) >= 2]
                            if len(pts) >= 3:
                                rings.append(pts)
                return rings

            for pts in _extract_rings(coords):
                all_lons.extend([p[0] for p in pts])
                all_lats.extend([p[1] for p in pts])
                patches.append(Polygon(pts, closed=True))

        if not patches:
            _logger.warning('GeoJSON 中无有效多边形')
            return None

        min_lon, max_lon = min(all_lons), max(all_lons)
        min_lat, max_lat = min(all_lats), max(all_lats)

        fig, ax = plt.subplots(figsize=(10, 8), dpi=100)
        ax.set_xlim(min_lon, max_lon)
        ax.set_ylim(min_lat, max_lat)
        ax.set_aspect('equal')
        ax.axis('off')

        for p in patches:
            ax.add_patch(p)
            p.set_facecolor('white')    # 白色=可放文字
            p.set_edgecolor('none')

        ax.set_facecolor('black')
        fig.patch.set_facecolor('black')

        os.makedirs(os.path.dirname(mask_path), exist_ok=True)
        fig.savefig(mask_path, dpi=100, bbox_inches='tight', pad_inches=0, facecolor='black')
        plt.close(fig)

        _logger.info(f'中国地图 mask 已生成: {mask_path}')
        return mask_path

    except Exception as e:
        _logger.warning(f'生成中国地图 mask 失败: {e}')
        return None


def generate_wordcloud_data(top_n=60):
    """
    从数据库职位标题（post）中提取关键词，统计词频。

    注意：只从 post（标题）中提取，避免 content（描述）中
    大量福利、公司介绍、招聘用语造成的噪音。

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
        cursor.execute("SELECT post FROM data")
        rows = cursor.fetchall()
        db.close()
    except Exception as e:
        _logger.error("词云数据查询失败: %s", e)
        return {'success': False, 'total_jobs': 0, 'words': [], 'error': str(e)}

    if not rows:
        return {'success': True, 'total_jobs': 0, 'words': []}

    # 只拼接职位标题
    all_text = []
    for r in rows:
        post = (r[0] or '').strip()
        if post:
            all_text.append(post)
    full_text = ' '.join(all_text)

    # jieba 分词
    words = jieba.lcut(full_text)

    # 过滤 + 归一化
    counter = Counter()
    for w in words:
        w = w.strip().lower()
        # 跳过单字、纯数字、标点、空白、职位ID格式
        if (len(w) < 2 or w.isdigit() or
                re.match(r'^[\d\.\-\s/,;:!?()（）【】]+$', w) or
                re.match(r'^j\d+$', w)):
            continue
        # 白名单优先（技术词不受停用词影响）
        if w in WHITELIST:
            w_upper = TERM_NORMALIZE.get(w, w)
            counter[w_upper] += 1
            continue
        if w in STOP_WORDS:
            continue
        # 同义词归一化
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
