"""
薪资预测模型。

基于 (城市, 职位类别, 学历, 经验) 元组训练线性回归。模型特意设计得简单:
训练数据约 500 行级别,比线性回归更复杂的模型会严重过拟合。

训练两个版本模型进行对比:
* 仅使用 city + category (基线模型)
* 使用 city + category + education + experience (全特征集)

报告 R² 的提升(或无提升),以便调用方判断学历和经验字段是否为当前数据集增加预测信号。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import config
from analysis.jobtitle import classify
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.metrics import r2_score, mean_absolute_error


def get_rows():
    try:
        db = sqlite3.connect(config.DB_PATH)
        cursor = db.cursor()
        cursor.execute("SELECT post, address, salary_min, salary_max, edu, exper FROM data")
        rows = cursor.fetchall()
        db.close()
        return rows
    except sqlite3.Error:
        return []


def build_dataset(include_edu_exper=True):
    rows = get_rows()
    X, y = [], []
    for post, addr, smin, smax, edu, exper in rows:
        if not smin and not smax:
            continue
        city = addr.split('-')[0] if addr else 'Unknown'
        category = classify(post)
        avg_salary = (smin + smax) / 2
        if include_edu_exper:
            X.append([city, category, edu or '不限', exper or '经验不限'])
        else:
            X.append([city, category])
        y.append(avg_salary)
    return np.array(X, dtype=object), np.array(y)


def build_model(n_features):
    return Pipeline([
        ('prep', ColumnTransformer([
            ('cat', OneHotEncoder(handle_unknown='ignore'), list(range(n_features))),
        ])),
        ('reg', LinearRegression()),
    ])


def _train_one(include_edu_exper, random_state=42):
    X, y = build_dataset(include_edu_exper)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=random_state
    )
    model = build_model(X.shape[1])
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    r2 = r2_score(y_test, y_pred)
    mae = mean_absolute_error(y_test, y_pred)
    baseline_pred = np.full_like(y_test, y_train.mean())
    baseline_mae = mean_absolute_error(y_test, baseline_pred)

    return {
        'model': model, 'r2': r2, 'mae': mae, 'baseline_mae': baseline_mae,
        'n_train': len(X_train), 'n_test': len(X_test),
        'include_edu_exper': include_edu_exper,
    }


def _train_rf(include_edu_exper, random_state=42):
    """使用 RandomForestRegressor 训练模型,用于与线性回归对比。"""
    X, y = build_dataset(include_edu_exper)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=random_state
    )
    model = Pipeline([
        ('prep', ColumnTransformer([
            ('cat', OneHotEncoder(handle_unknown='ignore'), list(range(X.shape[1]))),
        ])),
        ('reg', RandomForestRegressor(n_estimators=100, random_state=random_state, n_jobs=-1)),
    ])
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    r2 = r2_score(y_test, y_pred)
    mae = mean_absolute_error(y_test, y_pred)
    baseline_pred = np.full_like(y_test, y_train.mean())
    baseline_mae = mean_absolute_error(y_test, baseline_pred)

    return {
        'model': model, 'r2': r2, 'mae': mae, 'baseline_mae': baseline_mae,
        'n_train': len(X_train), 'n_test': len(X_test),
        'include_edu_exper': include_edu_exper,
    }


def train_and_evaluate(random_state=42):
    """训练三个模型:基线(城市+类别)、全特征线性回归、全特征随机森林。
    返回全特征线性模型的结果字典,附加基线 R² 和随机森林 R² 用于对比。"""
    old_result = _train_one(include_edu_exper=False, random_state=random_state)
    new_result = _train_one(include_edu_exper=True, random_state=random_state)
    rf_result = _train_rf(include_edu_exper=True, random_state=random_state)

    new_result['old_r2'] = old_result['r2']
    new_result['old_mae'] = old_result['mae']
    new_result['rf_r2'] = rf_result['r2']
    new_result['rf_mae'] = rf_result['mae']
    new_result['rf_model'] = rf_result['model']

    # 记录训练时观察到的类别水平,以便下游调用方在请求值未见过时发出警告
    X, _ = build_dataset(include_edu_exper=True)
    new_result['valid_edu'] = sorted(set(X[:, 2]))
    new_result['valid_exper'] = sorted(set(X[:, 3]))
    new_result['valid_city'] = sorted(set(X[:, 0]))
    new_result['valid_category'] = sorted(set(X[:, 1]))
    return new_result


def predict_salary(model, city, category, edu='不限', exper='经验不限'):
    pred = model.predict(np.array([[city, category, edu, exper]], dtype=object))
    return round(float(pred[0]), 1)


def _fuzzy_match(value, valid_values, fallback):
    """返回 (匹配后的值, 是否发生替换) 元组。
    如果 value 不在 valid_values 中,尝试找到包含 value 的条目。否则回退到提供的默认值。
    """
    if not value or value in valid_values:
        return (value or fallback), False
    for v in valid_values:
        if value in v:
            return v, True
    return fallback, True


def predict_salary_safe(model, city, category, edu, exper, valid_edu, valid_exper,
                        valid_city=None, valid_category=None):
    """predict_salary 的包装函数:当调用方传入训练数据中未见过的类别时发出警告
    (而不是默默给出错误预测)。OneHotEncoder(handle_unknown='ignore') 会丢弃未见过的列,
    这会悄悄改变特征向量,导致无意义预测。
    """
    warnings = []
    matched_edu, edu_sub = _fuzzy_match(edu, valid_edu, '不限')
    matched_exper, exper_sub = _fuzzy_match(exper, valid_exper, '经验不限')
    if edu_sub:
        warnings.append(f'学历输入"{edu}"不在训练数据标准取值中,已模糊匹配/替换为"{matched_edu}"')
    if exper_sub:
        warnings.append(f'经验输入"{exper}"不在训练数据标准取值中,已模糊匹配/替换为"{matched_exper}"')
    if valid_city and city and city not in valid_city:
        warnings.append(f'城市"{city}"不在训练数据中,预测结果可能不准确')
    if valid_category and category and category not in valid_category:
        warnings.append(f'职位类别"{category}"不在训练数据中,预测结果可能不准确')

    pred = predict_salary(model, city, category, matched_edu, matched_exper)
    return pred, matched_edu, matched_exper, warnings


def _contains_word(needle, haystack):
    """双向包含匹配，但要求 needle 至少 2 个字符，防止单字误匹配。"""
    if not needle or not haystack:
        return False
    if len(needle) < 2:
        return needle == haystack
    return needle in haystack or haystack in needle


def lookup_salary_range(city='', category='', edu='', exper=''):
    """数据库驱动的薪资参考查询 — 零模型，纯统计。

    从数据库中筛选匹配 (城市 + 职位类别 + 学历 + 经验) 的岗位，
    返回真实薪资的描述性统计（中位数、均值、范围、分位数）。

    Args:
        city: 城市名称（如"北京"、"上海"，模糊匹配）
        category: 职位类别（如"后端开发"、"Web/前端"，双向模糊匹配）
        edu: 学历过滤（空或"不限"表示不过滤）
        exper: 经验过滤（空或"经验不限"表示不过滤）

    Returns:
        dict: {
            count, median, mean, min, max, p25, p75  — 薪资统计，单位K
            或 {count, message} — 数据不足时
        }
    """
    try:
        rows = get_rows()
    except Exception:
        return {'count': 0, 'message': '数据库读取失败，请稍后重试'}
    matched = []
    for post, addr, smin, smax, edu_val, exper_val in rows:
        if not smin and not smax:
            continue
        # 城市过滤（模糊：输入"北京"能匹配"北京-海淀区"，但"海"不会误匹配"上海"）
        if city:
            addr_city = addr.split('-')[0] if addr else ''
            if not _contains_word(city, addr_city):
                continue
        # 类别过滤（双向模糊：输入"后端"能匹配"后端开发"）
        if category:
            cat = classify(post)
            if not _contains_word(category, cat):
                continue
        # 学历过滤（要求至少2字符匹配，防单字误匹配）
        if edu and edu != '不限':
            if not edu_val or not _contains_word(edu, edu_val):
                continue
        # 经验过滤
        if exper and exper != '经验不限':
            if not exper_val or not _contains_word(exper, exper_val):
                continue
        matched.append((smin + smax) / 2)

    if len(matched) < 3:
        msg = '匹配岗位数量不足 (需要≥3)，请放宽条件' if matched else '未找到匹配岗位'
        return {'count': len(matched), 'message': msg}

    arr = np.array(matched)
    return {
        'count': len(matched),
        'median': round(float(np.median(arr)), 1),
        'mean': round(float(np.mean(arr)), 1),
        'min': round(float(np.min(arr)), 1),
        'max': round(float(np.max(arr)), 1),
        'p25': round(float(np.percentile(arr, 25)), 1),
        'p75': round(float(np.percentile(arr, 75)), 1),
    }


if __name__ == '__main__':
    print('=== 薪资参考查询（数据库驱动，零模型）===\n')
    for city, cat in [('北京', '后端开发'), ('上海', 'Web/前端'), ('深圳', '数据')]:
        r = lookup_salary_range(city, cat)
        if 'message' in r:
            print(f'  {city} + {cat}: {r["message"]}')
        else:
            print(f'  {city} + {cat}: '
                  f'中位数={r["median"]}K  均值={r["mean"]}K  '
                  f'范围 {r["min"]}-{r["max"]}K  (共{r["count"]}个岗位)')
    print('\n=== 旧版 ML 模型（保留兼容，仅供参考）===')
    result = train_and_evaluate()
    print(f"训练样本: {result['n_train']}, 测试样本: {result['n_test']}")
    print(f"线性回归 R²={result['r2']:.3f}  MAE={result['mae']:.2f}K")
    print(f"随机森林 R²={result['rf_r2']:.3f}  MAE={result['rf_mae']:.2f}K")
    print(f"注意: R² 为负表示模型预测不如直接猜平均值，已用 lookup_salary_range() 替代。")
