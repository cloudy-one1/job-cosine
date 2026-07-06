"""
学历溢价分析 — 同城市同方向下，不同学历的薪资对比。

回答：硕士比本科多拿多少？本科比大专多拿多少？

对每个 (城市, 方向) 组合，计算各学历层级的平均薪资，
并计算相邻层级的溢价百分比。
"""
import sqlite3
import config
import logging
import numpy as np
from analysis.jobtitle import classify

_logger = logging.getLogger('modeling.edu_premium')

# 学历归一化
EDU_NORMALIZE = {
    '博士': '博士', '博士研究生': '博士',
    '硕士': '硕士', '硕士研究生': '硕士', 'MBA': '硕士',
    '本科': '本科', '大学本科': '本科', '本科及以上': '本科',
    '大专': '大专', '大学专科': '大专', '大专及以上': '大专',
    '高中': '高中', '中专': '高中', '中技': '高中',
    '初中': '初中及以下', '不限': '不限',
}
EDU_RANK = {'博士': 5, '硕士': 4, '本科': 3, '大专': 2, '高中': 1, '初中及以下': 0, '不限': -1}


def _normalize_edu(edu_raw):
    """学历归一化。"""
    if not edu_raw:
        return '不限'
    for pattern, normalized in sorted(EDU_NORMALIZE.items(), key=lambda x: -len(x[0])):
        if pattern in edu_raw:
            return normalized
    return edu_raw


def compute_edu_premium(min_per_group=3):
    """计算学历溢价分析数据。

    Args:
        min_per_group: 每组 (城市, 方向, 学历) 最少岗位数

    Returns:
        dict: {
            premiums: [{city, category, levels: {edu: {count, avg_salary}}, premiums: [{from, to, premium_pct}]}],
            overall: {edu: {count, avg_salary, median}} (全局学历薪资分布),
            total_rows: int,
        }
    """
    try:
        db = sqlite3.connect(config.DB_PATH)
        db.row_factory = sqlite3.Row
        cursor = db.cursor()
        cursor.execute(
            "SELECT post, address, salary_min, salary_max, edu FROM data"
        )
        rows = cursor.fetchall()
        db.close()
    except sqlite3.Error as e:
        _logger.warning('compute_edu_premium 读取数据库失败: %s', e)
        return {'error': '数据库读取失败', 'total_rows': 0}

    if not rows:
        return {'error': '数据库中没有岗位数据，请先采集', 'total_rows': 0}

    # 聚合：(city, category, edu) → [salaries]
    group_salaries = {}
    overall_edu = {}  # edu → [salaries] 全局分布

    for row in rows:
        addr = row['address'] or ''
        city = addr.split('-')[0].strip() if addr else '未知'
        smin = row['salary_min']
        smax = row['salary_max']
        if not smin or not smax or (smin + smax) <= 0:
            continue
        avg_sal = (smin + smax) / 2

        category = classify(row['post'] or '')
        edu = _normalize_edu(row['edu'])

        key = (city, category, edu)
        if key not in group_salaries:
            group_salaries[key] = []
        group_salaries[key].append(avg_sal)

        if edu not in overall_edu:
            overall_edu[edu] = []
        overall_edu[edu].append(avg_sal)

    if not group_salaries:
        return {'error': '没有有效薪资数据', 'total_rows': len(rows)}

    # 计算溢价
    # 先聚合为 (city, category) → {edu: {count, avg, arr}}
    pair_edu = {}
    for (city, cat, edu), salaries in group_salaries.items():
        pair_key = (city, cat)
        if pair_key not in pair_edu:
            pair_edu[pair_key] = {}
        pair_edu[pair_key][edu] = {
            'count': len(salaries),
            'avg_salary': round(float(np.mean(salaries)), 1),
            'median': round(float(np.median(salaries)), 1),
        }

    # 筛选：至少有两个学历层级且每个层级 ≥ min_per_group
    premiums = []
    for (city, cat), edu_data in pair_edu.items():
        if len(edu_data) < 2:
            continue
        # 过滤数量不足的层级
        filtered = {e: d for e, d in edu_data.items() if d['count'] >= min_per_group}
        if len(filtered) < 2:
            continue

        # 按学历等级排序
        sorted_edus = sorted(filtered.keys(), key=lambda e: EDU_RANK.get(e, -2))
        # 计算相邻层级溢价
        prem_list = []
        for i in range(len(sorted_edus) - 1):
            lower_key = sorted_edus[i]
            higher_key = sorted_edus[i + 1]
            lower_sal = filtered[lower_key]['avg_salary']
            higher_sal = filtered[higher_key]['avg_salary']
            if lower_sal > 0:
                pct = round((higher_sal - lower_sal) / lower_sal * 100, 1)
            else:
                pct = 0
            prem_list.append({
                'from': lower_key,
                'to': higher_key,
                'from_avg': lower_sal,
                'to_avg': higher_sal,
                'premium_pct': pct,
            })

        if prem_list:
            premiums.append({
                'city': city,
                'category': cat,
                'levels': {e: {'count': d['count'], 'avg_salary': d['avg_salary']}
                          for e, d in filtered.items()},
                'premiums': prem_list,
            })

    # 整体学历分布
    overall = {}
    for edu, salaries in overall_edu.items():
        if len(salaries) >= min_per_group:
            arr = np.array(salaries)
            overall[edu] = {
                'count': len(salaries),
                'avg_salary': round(float(np.mean(arr)), 1),
                'median': round(float(np.median(arr)), 1),
                'p25': round(float(np.percentile(arr, 25)), 1),
                'p75': round(float(np.percentile(arr, 75)), 1),
            }

    return {
        'premiums': premiums,
        'overall': overall,
        'total_rows': len(rows),
    }


if __name__ == '__main__':
    import json
    result = compute_edu_premium()
    print(json.dumps(result, ensure_ascii=False, indent=2))
