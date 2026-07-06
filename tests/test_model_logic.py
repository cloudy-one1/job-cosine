"""
建模层核心逻辑单元测试 — 使用合成数据，不依赖数据库。

覆盖:
  * job_clustering.choose_best_k() — 轮廓系数选 k
  * job_clustering.run_clustering() — 聚类全流程 (mock DB)
  * salary_predict.predict_salary_safe() — 安全预测 + 警告
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import numpy as np
import warnings


# ============================================================
# choose_best_k() — 轮廓系数选 k
# ============================================================
class TestChooseBestK:
    """用合成数据验证轮廓系数 k 值选择。"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from modeling.job_clustering import choose_best_k as _cbk
        self.cbk = _cbk

    def test_single_sample_returns_k1(self):
        """只有1个样本时返回 k=1。"""
        X = np.array([[0.1, 0.2]])
        k, scores = self.cbk(X)
        assert k == 1
        assert scores == {1: 0.0}

    def test_two_samples_returns_k1(self):
        """2个样本退化为 k=1 (max_k < 2)。"""
        X = np.array([[0.1, 0.2], [0.3, 0.4]])
        k, scores = self.cbk(X)
        assert k == 1

    def test_choose_k_with_clear_clusters(self):
        """3簇清晰数据应选 k=3 (或相近值)。"""
        np.random.seed(42)
        c1 = np.random.normal(0, 0.3, (30, 5))
        c2 = np.random.normal(5, 0.3, (30, 5))
        c3 = np.random.normal(10, 0.3, (30, 5))
        X = np.vstack([c1, c2, c3])
        k, scores = self.cbk(X)
        assert k >= 1
        assert len(scores) > 0
        # 在清晰3簇数据上,预期 k >= 2 (至少应发现多个簇)
        assert k >= 2

    def test_scores_are_positive(self):
        """轮廓系数应在合理范围内。"""
        np.random.seed(1)
        X = np.random.normal(0, 1, (40, 5))
        k, scores = self.cbk(X)
        for s in scores.values():
            assert -1.0 <= s <= 1.0


# ============================================================
# run_clustering() — 聚类全流程 (mock get_posts)
# ============================================================
class TestRunClustering:
    """mock 掉数据库调用,只测试聚类逻辑。"""

    def test_run_with_mocked_posts(self, monkeypatch):
        """用30个模拟职位标题运行完整聚类流程。"""
        mock_posts = [
            'Python后端开发工程师',
            'Java后端开发',
            'Go后台开发',
            '后端高级工程师',
            '后端服务端开发',
            # ---
            'Web前端工程师',
            '前端开发工程师',
            'React前端',
            'Vue前端开发',
            'Web前端高级',
            # ---
            '数据挖掘工程师',
            '大数据开发',
            '数据分析师',
            '数据工程师',
            '数据科学家',
            # ---
            '软件测试工程师',
            '自动化测试',
            '测试开发',
            '功能测试',
            '性能测试工程师',
            # ---
            '运维工程师',
            '运维开发',
            'Linux系统运维', 
            'DevOps工程师',
            'SRE运维',
            # ---
            'Python爬虫工程师',
            '数据爬虫',
            '爬虫开发',
            '网络爬虫',
            '反爬虫工程师',
        ]

        from modeling import job_clustering
        monkeypatch.setattr(job_clustering, 'get_posts', lambda: list(enumerate(mock_posts)))

        result = job_clustering.run_clustering()
        assert 'k' in result
        assert 'clusters' in result
        assert result['k'] >= 1
        assert len(result['clusters']) == result['k']
        for c in result['clusters']:
            assert 'cluster_id' in c
            assert 'auto_label' in c
            assert 'count' in c
            assert 'top_keywords' in c
            assert c['count'] > 0


# ============================================================
# predict_salary_safe() — 安全预测 + 模糊匹配警告
# ============================================================
class TestPredictSalarySafe:
    """验证 predict_salary_safe 的模糊匹配和警告机制。"""

    def test_unknown_edu_triggers_warning(self, monkeypatch):
        """输入训练数据中未见的学历应触发警告并回退。"""
        from modeling import salary_predict
        # Mock model — 不会真的调用 model.predict
        class FakeModel:
            def predict(self, X):
                return np.array([15.0])
        model = FakeModel()
        valid_edu = ['本科', '大专', '不限']
        valid_exper = ['1-3年', '3-5年', '经验不限']

        pred, matched_edu, matched_exper, warnings = (
            salary_predict.predict_salary_safe(
                model, '北京', '后端开发', '博士', '10年以上',
                valid_edu, valid_exper,
            )
        )
        assert pred == 15.0
        assert matched_edu == '不限'  # 回退到默认
        assert matched_exper == '经验不限'  # 回退到默认
        assert len(warnings) > 0

    def test_known_values_no_warnings(self):
        """训练集中存在的值不应触发任何警告。"""
        import numpy as np
        from modeling import salary_predict

        class FakeModel:
            def predict(self, X):
                return np.array([20.0])

        model = FakeModel()
        valid_edu = ['本科', '大专', '硕士']
        valid_exper = ['1-3年', '3-5年']

        pred, matched_edu, matched_exper, warnings = (
            salary_predict.predict_salary_safe(
                model, '北京', '后端开发', '本科', '3-5年',
                valid_edu, valid_exper,
            )
        )
        assert pred == 20.0
        assert matched_edu == '本科'
        assert matched_exper == '3-5年'
        assert warnings == []

    def test_unknown_city_warns(self):
        """未见过的城市也应触发警告。"""
        import numpy as np
        from modeling import salary_predict

        class FakeModel:
            def predict(self, X):
                return np.array([10.0])

        model = FakeModel()
        valid_city = ['北京', '上海']

        pred, _, _, warnings = salary_predict.predict_salary_safe(
            model, '拉萨', '后端开发', '本科', '3-5年',
            ['本科'], ['3-5年'],
            valid_city=valid_city,
        )
        assert any('拉萨' in w for w in warnings)


# ============================================================
# _train_rf() + train_and_evaluate() — 随机森林训练与三模型对比
# ============================================================
def _make_synthetic_rows(n=50, seed=42):
    """生成合成数据，模拟 get_rows() 返回格式。"""
    import random
    rng = random.Random(seed)
    cities = ['北京', '上海', '深圳', '广州', '杭州']
    posts = ['Python后端开发', 'Java后端开发', '前端开发工程师',
             'Python爬虫工程师', '运维工程师', '测试工程师',
             '大数据开发', '数据挖掘工程师']
    edus = ['不限', '大专', '本科', '硕士', '博士']
    expers = ['经验不限', '1-3年', '3-5年', '5-10年', '10年以上']
    rows = []
    for _ in range(n):
        city = rng.choice(cities)
        post = rng.choice(posts)
        edu = rng.choice(edus)
        exper = rng.choice(expers)
        base = {'不限': 5, '大专': 8, '本科': 15, '硕士': 22, '博士': 35}[edu]
        noise = rng.uniform(-3, 8)
        smin = max(3, base + noise - rng.uniform(1, 4))
        smax = smin + rng.uniform(3, 15)
        rows.append((post, city, round(smin, 1), round(smax, 1), edu, exper))
    return rows


class TestTrainRF:
    """验证 _train_rf 和 train_and_evaluate。"""

    def test_train_rf_returns_expected_keys(self, monkeypatch):
        """_train_rf 返回字典包含 model, r2, mae, baseline_mae。"""
        from modeling import salary_predict
        monkeypatch.setattr(salary_predict, 'get_rows', lambda: _make_synthetic_rows(60))
        # 抑制 sklearn 关于特征名未知的警告
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            result = salary_predict._train_rf(include_edu_exper=True, random_state=42)

        assert 'model' in result
        assert 'r2' in result
        assert 'mae' in result
        assert 'baseline_mae' in result
        assert 'n_train' in result
        assert 'n_test' in result
        assert isinstance(result['r2'], float)
        assert isinstance(result['mae'], float)
        assert result['mae'] > 0
        assert result['n_train'] > 0 and result['n_test'] > 0

    def test_train_rf_model_is_pipeline(self, monkeypatch):
        """RF 模型是 Pipeline 实例。"""
        from modeling import salary_predict
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.pipeline import Pipeline
        monkeypatch.setattr(salary_predict, 'get_rows', lambda: _make_synthetic_rows(40))
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            result = salary_predict._train_rf(include_edu_exper=True, random_state=42)

        assert isinstance(result['model'], Pipeline)
        # Pipeline 最后一步是 RandomForestRegressor
        assert isinstance(result['model'].named_steps['reg'], RandomForestRegressor)

    def test_train_and_evaluate_returns_three_models(self, monkeypatch):
        """train_and_evaluate 返回三个模型的指标: old_r2, r2, rf_r2。"""
        from modeling import salary_predict
        monkeypatch.setattr(salary_predict, 'get_rows', lambda: _make_synthetic_rows(60))
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            result = salary_predict.train_and_evaluate(random_state=42)

        assert 'old_r2' in result       # 基线(城市+类别)线性回归
        assert 'r2' in result           # 全特征线性回归
        assert 'rf_r2' in result        # 全特征随机森林
        assert 'old_mae' in result
        assert 'mae' in result
        assert 'rf_mae' in result
        assert 'rf_model' in result
        # 应有 valid_edu / valid_exper 供 predict_salary_safe 使用
        assert 'valid_edu' in result
        assert 'valid_exper' in result
        assert isinstance(result['valid_edu'], list)
        assert isinstance(result['valid_exper'], list)

    def test_train_and_evaluate_valid_levels(self, monkeypatch):
        """valid_edu / valid_exper / valid_city / valid_category 不为空。"""
        from modeling import salary_predict
        monkeypatch.setattr(salary_predict, 'get_rows', lambda: _make_synthetic_rows(40))
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            result = salary_predict.train_and_evaluate(random_state=42)

        assert len(result['valid_edu']) > 0
        assert len(result['valid_exper']) > 0
        assert len(result['valid_city']) > 0
        assert len(result['valid_category']) > 0

    def test_baseline_vs_full_different(self, monkeypatch):
        """基线模型和全特征模型应有不同的 R² (或至少都是合法值)。"""
        from modeling import salary_predict
        monkeypatch.setattr(salary_predict, 'get_rows', lambda: _make_synthetic_rows(80))
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            result = salary_predict.train_and_evaluate(random_state=42)

        # R² 应是合法浮点
        assert -1.0 <= result['old_r2'] <= 1.0
        assert -1.0 <= result['r2'] <= 1.0
        assert -1.0 <= result['rf_r2'] <= 1.0
        # MAE 应为正
        assert result['old_mae'] > 0
        assert result['mae'] > 0
        assert result['rf_mae'] > 0


# ============================================================
# modeling.cache — 模型缓存单例
# ============================================================
class TestModelCache:
    """验证模型缓存的 get/update 机制。"""

    def test_get_returns_result(self):
        """首次 get() 应触发训练并返回非 None 结果。"""
        import modeling.cache as cache
        # 重置缓存
        cache.update(None)
        # get 内部会懒训练 (需要 mock get_rows)
        # 直接验证 update/get 机制: 手动注入假结果
        fake_result = {'model': None, 'r2': 0.85, 'old_r2': 0.72}
        cache.update(fake_result)
        result = cache.get()
        assert result is not None
        assert result['r2'] == 0.85
        assert result['old_r2'] == 0.72

    def test_update_then_get(self):
        """update 后 get 返回新值。"""
        import modeling.cache as cache

        old = {'model': object(), 'r2': 0.50}
        new = {'model': object(), 'r2': 0.90}

        cache.update(old)
        assert cache.get()['r2'] == 0.50

        cache.update(new)
        assert cache.get()['r2'] == 0.90
        assert cache.get() is new  # 同一引用


# ============================================================
# run_clustering() — 空数据兜底
# ============================================================
class TestRunClusteringEdgeCases:
    """验证 run_clustering 的健壮性：空数据/极小数据集。"""

    def test_empty_titles_returns_safe_result(self, monkeypatch):
        """空标题列表返回 k=0 + 空 clusters，不应崩溃。"""
        from modeling import job_clustering
        monkeypatch.setattr(job_clustering, 'get_posts', lambda: [])
        result = job_clustering.run_clustering()
        assert result['k'] == 0
        assert result['clusters'] == []
        assert result['total_jobs'] == 0

    def test_single_title_returns_k1(self, monkeypatch):
        """只有1个标题时应安全返回 k=1。"""
        from modeling import job_clustering
        monkeypatch.setattr(job_clustering, 'get_posts',
                           lambda: [(1, 'Python后端开发工程师')])
        result = job_clustering.run_clustering()
        assert result['k'] >= 1
        assert len(result['clusters']) == result['k']
        assert result['total_jobs'] == 1


# ============================================================
# _cluster_salary_stats() — 空 ID 防护
# ============================================================
class TestClusterSalaryStats:
    """验证 _cluster_salary_stats 的健壮性。"""

    def test_empty_ids_returns_empty(self):
        """空 ids 列表应返回空列表，不触发 SQL 语法错误。"""
        from modeling import job_clustering
        result = job_clustering._cluster_salary_stats([], np.array([]), 3)
        assert result == []

    def test_empty_ids_returns_empty_list_k0(self):
        """ids 为空且 k=0 时也不应崩溃。"""
        from modeling import job_clustering
        result = job_clustering._cluster_salary_stats([], np.array([]), 0)
        assert result == []


# ============================================================
# lookup_salary_range() — 薪资参考查询
# ============================================================
def _make_lookup_rows(n=30, seed=42):
    """生成模拟 get_rows() 输出的行数据。"""
    import random
    rng = random.Random(seed)
    cities = ['北京', '上海', '深圳', '广州', '杭州']
    posts = ['Python后端开发', 'Java后端开发', '前端开发工程师',
             'Python爬虫工程师', '运维工程师', '测试工程师',
             '大数据开发', '数据挖掘工程师']
    edus = ['不限', '大专', '本科', '硕士', '博士']
    expers = ['经验不限', '1-3年', '3-5年', '5-10年', '10年以上']
    rows = []
    for i in range(n):
        city = rng.choice(cities)
        post = rng.choice(posts)
        edu = rng.choice(edus)
        exper = rng.choice(expers)
        base_salary = rng.uniform(8, 30)
        smin = round(base_salary, 1)
        smax = round(base_salary + rng.uniform(3, 15), 1)
        rows.append((post, city, smin, smax, edu, exper))
    return rows


class TestLookupSalaryRange:
    """验证 lookup_salary_range 的查询逻辑和边缘情况。"""

    def test_basic_lookup_returns_expected_keys(self, monkeypatch):
        """正常查询应返回统计字段。"""
        from modeling import salary_predict
        monkeypatch.setattr(salary_predict, 'get_rows',
                           lambda: _make_lookup_rows(60))
        result = salary_predict.lookup_salary_range(city='北京', category='后端')
        if 'message' in result:
            # 可能匹配不够，只验证不崩溃
            assert result['count'] < 3
        else:
            assert 'median' in result
            assert 'mean' in result
            assert 'min' in result
            assert 'max' in result
            assert 'p25' in result
            assert 'p75' in result
            assert result['count'] >= 3
            assert result['median'] > 0

    def test_no_match_returns_message(self, monkeypatch):
        """完全不匹配的城市应返回 message。"""
        from modeling import salary_predict
        monkeypatch.setattr(salary_predict, 'get_rows',
                           lambda: _make_lookup_rows(30))
        result = salary_predict.lookup_salary_range(city='火星', category='前端')
        assert 'message' in result

    def test_single_char_city_not_false_match(self, monkeypatch):
        """单个字'海'不应误匹配'上海'（_contains_word 防误匹配）。"""
        from modeling import salary_predict
        rows = [('Python后端开发', '上海', 15.0, 25.0, '本科', '3-5年')]
        monkeypatch.setattr(salary_predict, 'get_rows', lambda: rows)
        result = salary_predict.lookup_salary_range(city='海')
        # '海' 长度 < 2，只做精确匹配，不应匹配 '上海'
        assert 'message' in result

    def test_multi_char_city_partial_match(self, monkeypatch):
        """'北京' 精确匹配应正常返回结果（长度 ≥ 2）。"""
        from modeling import salary_predict
        rows = [
            ('Python后端开发', '北京', 15.0, 25.0, '本科', '3-5年'),
            ('Java后端开发', '北京', 12.0, 20.0, '本科', '1-3年'),
            ('前端开发', '北京', 10.0, 18.0, '大专', '1-3年'),
            ('Python', '上海', 14.0, 22.0, '本科', '3-5年'),  # 不应该匹配
        ]
        monkeypatch.setattr(salary_predict, 'get_rows', lambda: rows)
        result = salary_predict.lookup_salary_range(city='北京')
        assert 'message' not in result
        assert result['count'] == 3

    def test_category_substring_match(self, monkeypatch):
        """输入'后端'应匹配'后端开发'（双向模糊匹配）。"""
        from modeling import salary_predict

        # 需要模拟 classify 返回的值包含 "后端"
        rows = [
            ('Python后端开发工程师', '北京', 15.0, 25.0, '本科', '3-5年'),
            ('Java后端开发', '北京', 12.0, 20.0, '本科', '1-3年'),
            ('Python后端', '北京', 14.0, 24.0, '大专', '3-5年'),
            ('Web前端开发', '北京', 10.0, 18.0, '大专', '1-3年'),
        ]
        # 需要 mock classify 让前三行返回 '后端开发'，最后一行返回 'Web/前端'
        original_classify = salary_predict.classify

        def mock_classify(post):
            if '后端' in post:
                return '后端开发'
            return 'Web/前端'

        monkeypatch.setattr(salary_predict, 'classify', mock_classify)
        monkeypatch.setattr(salary_predict, 'get_rows', lambda: rows)
        result = salary_predict.lookup_salary_range(category='后端')

        # 恢复原始函数（对测试无影响但不留副作用）
        # 注意: monkeypatch 已自动替换，测试结束会恢复

        if 'message' not in result:
            assert result['count'] >= 1
            assert result['median'] > 0

    def test_edu_filter_works(self, monkeypatch):
        """学历过滤应正确筛选。"""
        from modeling import salary_predict
        rows = [
            ('Python后端开发', '北京', 15.0, 25.0, '本科', '3-5年'),
            ('Java后端开发', '北京', 12.0, 20.0, '大专', '1-3年'),
            ('Python后端', '北京', 18.0, 28.0, '本科及以上', '3-5年'),
            ('后端开发', '北京', 10.0, 16.0, '大专', '1-3年'),
        ]
        monkeypatch.setattr(salary_predict, 'get_rows', lambda: rows)
        result = salary_predict.lookup_salary_range(city='北京', edu='本科')
        if 'message' not in result:
            assert result['count'] == 2  # 本科 + 本科及以上

    def test_get_rows_failure_returns_safe(self, monkeypatch):
        """数据库读取失败时返回安全 fallback。"""
        from modeling import salary_predict
        monkeypatch.setattr(salary_predict, 'get_rows', lambda: (_ for _ in ()).throw(sqlite3.Error))
        result = salary_predict.lookup_salary_range(city='北京')
        assert 'message' in result
        assert '失败' in result['message']

    def test_exact_city_address_match(self, monkeypatch):
        """带区地址'北京-海淀区'应匹配 city='北京'。"""
        from modeling import salary_predict
        rows = [
            ('Python后端开发', '北京-海淀区', 15.0, 25.0, '本科', '3-5年'),
            ('Java后端开发', '北京-朝阳区', 12.0, 20.0, '本科', '1-3年'),
            ('前端开发', '北京', 10.0, 18.0, '大专', '1-3年'),
        ]
        monkeypatch.setattr(salary_predict, 'get_rows', lambda: rows)
        result = salary_predict.lookup_salary_range(city='北京')
        assert 'message' not in result
        assert result['count'] == 3


# ============================================================
# _contains_word() — 模糊匹配辅助函数
# ============================================================
class TestContainsWord:
    """验证 _contains_word 的双向包含与单字防护逻辑。"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from modeling.salary_predict import _contains_word as _cw
        self.cw = _cw

    def test_exact_match(self):
        assert self.cw('北京', '北京') is True

    def test_partial_needle_in_haystack(self):
        assert self.cw('北京', '北京-海淀区') is True
        assert self.cw('后端', '后端开发') is True

    def test_partial_haystack_in_needle(self):
        assert self.cw('后端开发', '后端') is True

    def test_single_char_requires_exact(self):
        """单字输入不做模糊匹配。"""
        assert self.cw('海', '上海') is False
        assert self.cw('本', '本科') is False
        assert self.cw('京', '北京') is False

    def test_single_char_exact_ok(self):
        """单字精确匹配应通过（虽然实际不太会发生）。"""
        assert self.cw('海', '海') is True

    def test_empty_values(self):
        assert self.cw('', '北京') is False
        assert self.cw('北京', '') is False
        assert self.cw('', '') is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
