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
        a, b: 要对比的两个值,如 a='北京' b='上海',或 a='后端开发' b='Web/前端'。
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
        'description': '并排对比两个城市或两类岗位的薪资水平、职位数量、学历经验要求。参数: dim_type ("city" 或 "category"), a (第一个值), b (第二个值)。例如 compare_jobs("city","北京","上海") 或 compare_jobs("category","后端开发","Web/前端")。',
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
    print('\n=== predict_salary("北京", "爬虫/采集", "本科", "3-5年") ===')
    print(predict_salary('北京', '爬虫/采集', '本科', '3-5年'))
    print('\n=== edu_overview() ===')
    print(edu_overview())
    print('\n=== exper_overview() ===')
    print(exper_overview())
