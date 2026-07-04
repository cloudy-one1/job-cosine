"""
暴露给 ReAct agent 的工具。每个函数都通过 TOOLS 注册表按名称被调用。

约束:
* 仅查询本地 SQLite data 表或缓存模型,不碰网络。
* 返回 JSON 友好的数据(列表 / 字典 / 数字 / 字符串)。
* 不得编造数据库中不存在的数值。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from collections import Counter
import config
from analysis.jobtitle import classify
from analysis.xueli import xuelifun
from analysis.jinyan import jinyanfun
from analysis.region import extract_city
from modeling.salary_predict import predict_salary_safe as _predict_salary_safe
# 模型缓存 (与 app.py 共享同一个训练好的模型实例,消除重复训练)
from modeling.cache import get as _get_model_result

# 保留 set_model_result 别名以保持向后兼容;新代码应直接用 modeling.cache.update()
from modeling.cache import update as set_model_result


def edu_overview() -> list:
    """所有职位的学历分布统计。"""
    return [{'edu': e, 'count': c} for e, c in xuelifun()]


def exper_overview() -> list:
    """所有职位的工作经验要求分布统计。"""
    return [{'exper': e, 'count': c} for e, c in jinyanfun()]


def predict_salary(city: str, category: str, edu: str = '不限', exper: str = '经验不限') -> dict:
    """基于城市 + 职位类别 + 学历 + 经验,使用缓存的线性回归模型预测月薪(千元)。"""
    model_result = _get_model_result()
    pred, matched_edu, matched_exper, warns = _predict_salary_safe(
        model_result['model'], city, category, edu, exper,
        model_result['valid_edu'], model_result['valid_exper'],
    )
    result = {
        'city': city,
        'category': category,
        'edu': matched_edu,
        'exper': matched_exper,
        'predicted_salary_k': pred,
        'model_r2': round(model_result['r2'], 2),
        'note': f"模型 R2 = {model_result['r2']:.2f}(加入学历与经验特征前为 {model_result['old_r2']:.2f})。样本量较小,预测仅供参考。",
    }
    if warns:
        result['input_warnings'] = warns
    return result


def _connect():
    return sqlite3.connect(config.DB_PATH)


def query_jobs(keyword: str) -> dict:
    """按职位名称关键词模糊搜索,返回数量、薪资统计、城市排行。"""
    db = _connect()
    cursor = db.cursor()
    cursor.execute(
        "SELECT post, address, salary_min, salary_max FROM data WHERE post LIKE ?",
        (f'%{keyword}%',)
    )
    rows = cursor.fetchall()
    db.close()

    if not rows:
        return {'keyword': keyword, 'count': 0, 'message': '未找到匹配职位'}

    salaries = [(r[2] + r[3]) / 2 for r in rows if r[2] or r[3]]
    cities = {}
    for r in rows:
        city = r[1].split('-')[0] if r[1] else '未知'
        cities[city] = cities.get(city, 0) + 1
    top_cities = sorted(cities.items(), key=lambda x: -x[1])[:3]

    return {
        'keyword': keyword,
        'count': len(rows),
        'avg_salary_k': round(sum(salaries) / len(salaries), 1) if salaries else 0,
        'min_salary_k': round(min(salaries), 1) if salaries else 0,
        'max_salary_k': round(max(salaries), 1) if salaries else 0,
        'top_cities': top_cities,
    }


def category_overview() -> list:
    """按规则分类后的职位类别分布与各类别平均薪资。"""
    db = _connect()
    cursor = db.cursor()
    cursor.execute("SELECT post, salary_min, salary_max FROM data")
    rows = cursor.fetchall()
    db.close()

    cat_data = {}
    for post, smin, smax in rows:
        cat = classify(post)
        cat_data.setdefault(cat, []).append((smin + smax) / 2 if (smin or smax) else 0)

    result = []
    for cat, salaries in sorted(cat_data.items(), key=lambda x: -len(x[1])):
        valid = [s for s in salaries if s > 0]
        avg = round(sum(valid) / len(valid), 1) if valid else 0
        result.append({'category': cat, 'count': len(salaries), 'avg_salary_k': avg})
    return result


def city_overview() -> list:
    """各城市职位数量与平均薪资。"""
    db = _connect()
    cursor = db.cursor()
    cursor.execute("SELECT address, salary_min, salary_max FROM data")
    rows = cursor.fetchall()
    db.close()

    city_data = {}
    for addr, smin, smax in rows:
        city = extract_city(addr)
        city_data.setdefault(city, []).append((smin + smax) / 2 if (smin or smax) else 0)

    result = []
    for city, salaries in sorted(city_data.items(), key=lambda x: -len(x[1])):
        valid = [s for s in salaries if s > 0]
        avg = round(sum(valid) / len(valid), 1) if valid else 0
        result.append({'city': city, 'count': len(salaries), 'avg_salary_k': avg})
    return result


def compare_jobs(dim_type: str, a: str, b: str) -> dict:
    """并排对比两个城市或两个职位类别的招聘数据。

    参数:
        dim_type: 'city' 按城市对比, 'category' 按类别对比。
        a, b: 要对比的两个值,如 a='北京' b='上海',或 a='后端开发' b='Web开发'。
    """
    db = _connect()
    cursor = db.cursor()
    cursor.execute("SELECT post, address, salary_min, salary_max, edu, exper FROM data")
    rows = cursor.fetchall()
    db.close()

    def _side(val):
        acc = {'count': 0, 'salaries': [], 'edu': Counter(), 'exper': Counter()}
        for post, addr, smin, smax, edu, exper in rows:
            if dim_type == 'city':
                match = val in (addr or '')
            else:
                match = classify(post) == val
            if match:
                acc['count'] += 1
                if smin or smax:
                    acc['salaries'].append((smin + smax) / 2)
                if edu:
                    acc['edu'][edu] += 1
                if exper:
                    acc['exper'][exper] += 1
        sal_list = acc['salaries']
        return {
            'value': val,
            'count': acc['count'],
            'avg_salary_k': round(sum(sal_list) / len(sal_list), 1) if sal_list else 0,
            'min_salary_k': round(min(sal_list), 1) if sal_list else 0,
            'max_salary_k': round(max(sal_list), 1) if sal_list else 0,
            'top_edu': acc['edu'].most_common(3),
            'top_exper': acc['exper'].most_common(3),
        }

    return {
        'compare_type': dim_type,
        'a': _side(a),
        'b': _side(b),
    }


def extract_skills(keyword: str = '', top_n: int = 15) -> dict:
    """从职位标题/内容中提取高频技能关键词(正则+分词混合)。

    参数:
        keyword: 可选,筛选包含该关键词的职位标题后提取;留空则从全部职位提取。
        top_n: 返回前 N 个高频词,默认 15。
    """
    import jieba
    import re

    # ========== 技术关键词库(正则精确匹配) ==========
    _TECH_TERMS = [
        # 编程语言
        'Python', 'Java', 'C++', 'C#', 'JavaScript', 'TypeScript',
        'Rust', 'Kotlin', 'Swift', 'PHP', 'Ruby', 'Scala', 'Dart',
        'Matlab', 'R语言', 'Shell', 'Lua', 'Perl',
        # 前端
        'Vue', 'React', 'Angular', 'Node.js', 'Next.js', 'Nuxt',
        'Webpack', 'Vite', 'HTML5', 'CSS3', 'Sass', 'Less',
        'Bootstrap', 'jQuery', 'TypeScript', '小程序', 'H5',
        # 后端框架
        'Django', 'Flask', 'FastAPI', 'Spring', 'SpringBoot',
        'SpringCloud', 'MyBatis', 'Hibernate', '.NET', 'ASP.NET',
        'Express', 'NestJS', 'Tornado', 'Laravel',
        # 数据库
        'MySQL', 'PostgreSQL', 'MongoDB', 'Redis', 'Oracle',
        'Elasticsearch', 'SQLite', 'SQL Server', 'Cassandra',
        'Neo4j', 'ClickHouse', 'TDengine',
        # 大数据
        'Hadoop', 'Spark', 'Flink', 'Kafka', 'Hive', 'HBase',
        'Airflow', 'ETL', '数据仓库', '数据湖', 'MapReduce',
        # 云原生 DevOps
        'Docker', 'Kubernetes', 'K8s', 'Jenkins', 'GitLab', 'CI/CD',
        'AWS', 'Azure', '阿里云', '腾讯云', '华为云',
        'Nginx', 'Tomcat', 'Linux', 'Unix', 'Zabbix', 'Prometheus',
        # AI/ML
        'TensorFlow', 'PyTorch', '机器学习', '深度学习', 'NLP', 'CV',
        'OpenCV', 'scikit-learn', 'Keras', 'Pandas', 'NumPy',
        '大模型', 'LLM', 'RAG', 'LangChain', 'Transformer',
        # 嵌入式/硬件
        'PLC', '单片机', 'STM32', 'ARM', 'FPGA', 'DSP', 'MCU',
        '嵌入式', 'RTOS', 'FreeRTOS', 'RT-Thread', 'PCB',
        'Altium', 'Cadence', '西门子', '三菱', '欧姆龙', '施耐德', 'ABB',
        '触摸屏', 'HMI', 'SCADA', '伺服', '变频器', '步进电机',
        'RS485', 'RS232', 'CAN总线', 'Modbus', 'EtherCAT', 'Profinet',
        # 电气/自动化
        '电气', '自动化', '上位机', '下位机', '工控', 'DCS',
        'CAD', 'SolidWorks', 'UG', 'Pro/E', 'CATIA', 'Eplan',
        'EPLAN', 'AutoCAD', '仿真', 'LabVIEW', 'Matlab',
        # 数据分析
        'Tableau', 'PowerBI', 'Power BI', 'FineBI', 'SPSS', 'SAS',
        '数据挖掘', '数据分析', '可视化', '统计学',
        # 测试
        'Selenium', 'Appium', 'JMeter', 'Postman', 'Cypress',
        '自动化测试', '性能测试', '接口测试', '单元测试',
        # 通用技能
        'Git', 'SVN', 'RESTful', 'API', '微服务', '分布式',
        '高并发', '敏捷', 'Scrum', '多线程', 'MES', 'ERP', 'WMS',
        'ROS', 'SLAM', 'AGV', '机器视觉', 'Halcon',
    ]
    _tech_re = re.compile(
        '|'.join(re.escape(t) for t in sorted(_TECH_TERMS, key=len, reverse=True)),
        re.IGNORECASE,
    )

    # ========== 停用词(职位后缀/城市/公司/福利/无意义词) ==========
    _stop_words = {
        # 职位后缀/级别
        '工程师', '高级', '中级', '初级', '资深', '实习', '助理',
        '主管', '经理', '总监', '架构师', '专家', '顾问',
        '开发', '技术', '岗位', '方向', '相关',
        # 城市/地区名
        '北京', '上海', '广州', '深圳', '杭州', '南京', '苏州',
        '成都', '武汉', '西安', '重庆', '天津', '长沙', '合肥',
        '厦门', '福州', '郑州', '济南', '青岛', '大连', '沈阳',
        '无锡', '宁波', '东莞', '珠海', '佛山',
        '朝阳', '海淀', '浦东', '天河', '南山', '福田', '宝安',
        # 公司名常见后缀
        '科技', '信息', '集团', '有限', '公司', '技术',
        # 招聘无意义词
        '职位', '描述', '要求', '工作', '负责', '提供', '福利', '待遇',
        '五险一金', '周末双休', '餐补', '房补', '绩效', '奖金', '年终奖',
        '节日福利', '员工旅游', '带薪年假', '上升空间', '发展前景',
        '薪资', '面议', '全职', '学历', '经验', '双休', '单休',
        '行业', '技术员', '出差', '办公', '环境', '交通', '便利',
        '团队', '氛围', '培训', '晋升', '优秀', '良好', '具备',
        # 连接词/助词
        '的', '和', '及', '与', '等', '有', '在', '为', '或', '是',
        '了', '不', '可', '能', '会', '要', '将', '对', '从', '到',
        # 年限/数字
        '1-3', '3-5', '5-10', '一年', '三年', '五年', '以上', '以下',
        '不限', '若干', '若干年', '应届',
    }

    db = _connect()
    cursor = db.cursor()
    # 尝试读取 content 列(兼容旧表可能没有此列的情况)
    has_content = True
    try:
        if keyword:
            cursor.execute(
                "SELECT post, content FROM data WHERE post LIKE ?",
                (f'%{keyword}%',)
            )
        else:
            cursor.execute("SELECT post, content FROM data")
    except sqlite3.OperationalError:
        has_content = False
        if keyword:
            cursor.execute(
                "SELECT post FROM data WHERE post LIKE ?",
                (f'%{keyword}%',)
            )
        else:
            cursor.execute("SELECT post FROM data")
    raw_rows = cursor.fetchall()
    db.close()

    # 统一整理为 (post, content) 的格式
    rows = [(r[0], r[1] if has_content and len(r) > 1 else '') for r in raw_rows]

    if not rows:
        return {'keyword': keyword, 'total_jobs': 0,
                'skills': [], 'message': '未找到匹配的职位'}

    all_words = []
    for post, content in rows:
        post = post or ''
        content = content or ''
        # 拼接标题+内容作为分析文本
        text = f"{post} {content}"

        # 1) 正则匹配技术关键词
        for m in _tech_re.finditer(text):
            all_words.append(m.group().lower())

        # 2) jieba 分词补充(对未被正则覆盖的2-4字中文片段做补充)
        words = jieba.cut(post)  # 标题分词
        for w in words:
            w = w.strip()
            if len(w) < 2:
                continue
            if w in _stop_words:
                continue
            # 已经通过正则捕获的不重复计算
            # (这里简单判断: 纯英文/数字大概率已被正则命中,只补充中文)
            if re.search(r'[\u4e00-\u9fff]', w):
                # 过滤纯无意义中文短词(如"一名""我方"等)
                if len(w) <= 4 and re.match(r'^[\u4e00-\u9fff]{2,4}$', w):
                    all_words.append(w)

        if content:
            words_c = jieba.cut(content)
            for w in words_c:
                w = w.strip()
                if len(w) < 2 or w in _stop_words:
                    continue
                all_words.append(w)

    counter = Counter(all_words)

    # 去噪: 过滤掉只出现1次的词(通常是噪音)
    skills = [{'skill': w, 'count': c} for w, c in counter.most_common(top_n * 3)
              if c >= 2][:top_n]

    # 如果关键词过滤后结果太少,降低阈值重试
    if len(skills) < 5:
        skills = [{'skill': w, 'count': c} for w, c in counter.most_common(top_n)]

    return {
        'keyword': keyword or '全部',
        'total_jobs': len(rows),
        'skills': skills,
    }


# 工具注册表,agent 循环通过该表解析工具名称并构建系统提示中的工具列表
TOOLS = {
    'query_jobs': {
        'func': query_jobs,
        'description': '按职位名称关键词模糊搜索,返回数量、薪资统计、城市排行。参数: keyword (字符串)。',
    },
    'category_overview': {
        'func': category_overview,
        'description': '返回按规则分类后的职位类别分布与各类别平均薪资。无参数。',
    },
    'city_overview': {
        'func': city_overview,
        'description': '各城市职位数量与平均薪资。无参数。',
    },
    'edu_overview': {
        'func': edu_overview,
        'description': '返回所有职位的学历分布统计。无参数。',
    },
    'exper_overview': {
        'func': exper_overview,
        'description': '返回所有职位的工作经验要求分布统计。无参数。',
    },
    'predict_salary': {
        'func': predict_salary,
        'description': '使用线性回归模型预测月薪(千元)。参数: city (字符串), category (字符串), edu (可选字符串), exper (可选字符串)。',
    },
    'compare_jobs': {
        'func': compare_jobs,
        'description': '并排对比两个城市或两类岗位的薪资水平、职位数量、学历经验要求。参数: dim_type ("city" 或 "category"), a (第一个值), b (第二个值)。例如 compare_jobs("city","北京","上海")。',
    },
    'extract_skills': {
        'func': extract_skills,
        'description': '从职位标题中提取高频技能关键词词频。参数: keyword (可选,筛选关键词), top_n (可选,返回前N个,默认15)。例如 extract_skills("Python",10)。',
    },
}


if __name__ == '__main__':
    print('=== query_jobs("爬虫") ===')
    print(query_jobs('爬虫'))
    print('\n=== category_overview() (前5项) ===')
    for item in category_overview()[:5]:
        print(item)
    print('\n=== city_overview() ===')
    for item in city_overview():
        print(item)
    print('\n=== predict_salary("北京", "爬虫工程师", "本科", "3-5年") ===')
    print(predict_salary('北京', '爬虫工程师', '本科', '3-5年'))
    print('\n=== edu_overview() ===')
    print(edu_overview())
    print('\n=== exper_overview() ===')
    print(exper_overview())
