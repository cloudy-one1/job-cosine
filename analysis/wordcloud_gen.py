"""
词云生成模块 — 从职位标题+描述中提取高频技术关键词，生成词云图。

生成内容：
  1) 词频数据 (top N 关键词) → 传给模板用于 ECharts 词云渲染
  2) 词云 PNG 图片 → 保存到 static/wordcloud.png，兼容无 JS 场景

依赖: pip install wordcloud imageio matplotlib
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
# 参考 Buccal/job_Spider 的做法，把大小写/变体统一为规范写法
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
    'spring': 'Spring', 'springboot': 'SpringBoot',
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
    'sql': 'SQL',
}


# ========== 停用词 ==========
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
    '科技', '信息', '集团', '有限', '公司', '技术',
    # 招聘无意义词
    '职位', '描述', '要求', '工作', '负责', '提供', '福利', '待遇',
    '薪资', '面议', '全职', '学历', '经验', '双休', '单休',
    '行业', '技术员', '出差', '办公', '环境', '交通', '便利',
    '团队', '氛围', '培训', '晋升', '优秀', '良好', '具备',
    # 福利/补贴（高频噪音）
    '五险', '一金', '补贴', '带薪', '年假', '奖金', '年终', '绩效',
    '年终奖金', '绩效奖金', '补充', '公积金', '商业', '保险',
    '定期', '体检', '专业培训', '员工', '旅游', '周末', '双休',
    '餐补', '房补', '交通补贴', '通讯补贴', '节日', '生日',
    '弹性', '股票', '期权', '零食', '下午茶', '年度', '调薪',
    '六险', '二金', '三金', '包吃', '包住', '免费', '班车',
    # 连接词/助词
    '的', '和', '及', '与', '等', '有', '在', '为', '或', '是',
    '了', '不', '可', '能', '会', '要', '将', '对', '从', '到',
    # 通用动词/形容词
    '熟悉', '能力', '了解', '优先', '使用', '熟练', '基础', '学习',
    '具有', '专业', '扎实', '精通', '设计', '掌握', '善于', '至少',
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
    # 数据库通用词（保留具体的，去掉太泛的）
    '数据库',  # 太泛，MySQL/Redis 等具体名词会保留
    # 太泛的行业/通用词
    '计算机', '软件', '互联网', '通信', '网络', '通讯',
    '需求', '分析', '方案', '问题', '解决', '支持', '协助',
    '餐饮', '酒店', '销售', '客户', '市场', '运营',
    '医疗保险', '医疗', '保险', '养老', '失业', '工伤',
    '生育', '缴纳', '公积金', '住房', '加班', '补助',
    '住房补贴', '午餐', '晚餐', '提供', '完善', '丰厚',
    '保障', '按照国家', '规定', '享受', '签订', '合同',
    '标准', '国家', '法定', '劳动', '假期', '社保',
    '团建', '系统', '平台',  # 太泛
}


def _connect_db():
    """获取数据库连接"""
    import sqlite3
    from config import DB_PATH
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def generate_wordcloud_data(top_n=50):
    """
    从数据库中读取所有职位的 post + content，分词统计后返回词频数据。

    返回:
        dict: {
            'success': bool,
            'total_jobs': int,
            'words': [(word, count), ...],   # 词频列表, 按 count 降序
        }
    """
    try:
        db = _connect_db()
        cursor = db.cursor()
        try:
            cursor.execute("SELECT post, content FROM data")
        except Exception:
            cursor.execute("SELECT post FROM data")
        rows = cursor.fetchall()
        db.close()
    except Exception as e:
        _logger.error("词云数据查询失败: %s", e)
        return {'success': False, 'total_jobs': 0, 'words': [], 'error': str(e)}

    if not rows:
        return {'success': True, 'total_jobs': 0, 'words': []}

    # 拼接所有文本
    all_text = []
    for r in rows:
        post = (r[0] or '') if r[0] else ''
        content = (r[1] or '') if len(r) > 1 and r[1] else ''
        all_text.append(f'{post} {content}')

    full_text = ' '.join(all_text)

    # jieba 分词
    words = jieba.lcut(full_text)

    # 过滤 + 归一化
    counter = Counter()
    for w in words:
        w = w.strip().lower()
        # 跳过单字、纯数字、标点、空白
        if len(w) < 2 or w.isdigit() or re.match(r'^[\d\.\-\s/,;:!?()（）【】]+$', w):
            continue
        if w in STOP_WORDS:
            continue
        # 同义词归一化
        w = TERM_NORMALIZE.get(w, w)
        counter[w] += 1

    # 取 top N
    top_words = counter.most_common(top_n)

    return {
        'success': True,
        'total_jobs': len(rows),
        'words': top_words,
    }


def generate_wordcloud_png(output_path=None, top_n=100, width=900, height=500):
    """
    生成词云 PNG 图片（备用，无 JS 时展示静态图）。

    返回:
        str: 生成的 PNG 文件路径，或 None(失败时)
    """
    if output_path is None:
        output_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'static', 'wordcloud.png'
        )

    data = generate_wordcloud_data(top_n=top_n)
    if not data['success'] or not data['words']:
        return None

    try:
        from wordcloud import WordCloud
        import matplotlib
        matplotlib.use('Agg')  # 无 GUI 后端
        import matplotlib.pyplot as plt

        # 构建词频字典
        freq = {w: c for w, c in data['words']}

        wc = WordCloud(
            width=width, height=height,
            background_color='white',
            font_path=None,  # 使用系统默认字体
            max_words=top_n,
            colormap='viridis',
            prefer_horizontal=0.7,
            margin=5,
        )
        wc.generate_from_frequencies(freq)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        wc.to_file(output_path)
        _logger.info("词云 PNG 已生成: %s", output_path)
        return output_path

    except ImportError:
        _logger.warning("wordcloud 库未安装，跳过 PNG 生成")
        return None
    except Exception as e:
        _logger.error("词云 PNG 生成失败: %s", e)
        return None


# ---------- 命令行测试 ----------
if __name__ == '__main__':
    data = generate_wordcloud_data(top_n=30)
    print(f"总职位数: {data['total_jobs']}")
    print(f"Top 30 关键词:")
    for w, c in data['words']:
        print(f"  {w:20s} {c}")
    print(f"\n总词种数: {len(data['words'])}")

    # 生成 PNG
    result = generate_wordcloud_png()
    if result:
        print(f"\n词云图: {result}")
