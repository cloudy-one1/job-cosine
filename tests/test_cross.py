"""
交叉分析模块单元测试 — salary_vs_exper 和 salary_vs_edu。

mock _get_rows 返回合成数据,不依赖真实数据库。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ============================================================
# salary_vs_exper() — 薪资 vs 经验交叉统计
# ============================================================
class TestSalaryVsExper:
    """验证按经验等级分组的薪资统计。"""

    def test_returns_correct_structure(self, monkeypatch):
        """返回结构: labels, counts, avg_salaries。"""
        import analysis.cross as cross
        monkeypatch.setattr(cross, '_get_rows', lambda: [
            (10, 15, '本科', '1-3年'),
            (20, 30, '硕士', '3-5年'),
            (5, 10, '大专', '经验不限'),
        ])
        result = cross.salary_vs_exper()

        assert 'labels' in result
        assert 'counts' in result
        assert 'avg_salaries' in result
        assert len(result['labels']) == len(result['counts']) == len(result['avg_salaries'])

    def test_exper_order_preserved(self, monkeypatch):
        """经验等级按固定顺序排列。"""
        import analysis.cross as cross
        monkeypatch.setattr(cross, '_get_rows', lambda: [
            (10, 20, '本科', '5-10年'),
            (8, 12, '大专', '经验不限'),
            (15, 25, '硕士', '1-3年'),
            (20, 30, '博士', '3-5年'),
        ])
        result = cross.salary_vs_exper()
        expected_order = ['经验不限', '1-3年', '3-5年', '5-10年', '10年以上']
        assert result['labels'] == expected_order

    def test_correct_count_per_level(self, monkeypatch):
        """每个经验等级的计数正确。"""
        import analysis.cross as cross
        monkeypatch.setattr(cross, '_get_rows', lambda: [
            (10, 15, '本科', '1-3年'),
            (12, 18, '大专', '1-3年'),
            (20, 30, '硕士', '3-5年'),
            (5, 10, '大专', '经验不限'),
        ])
        result = cross.salary_vs_exper()

        assert result['counts'][0] == 1  # 经验不限
        assert result['counts'][1] == 2  # 1-3年
        assert result['counts'][2] == 1  # 3-5年
        assert result['counts'][3] == 0  # 5-10年
        assert result['counts'][4] == 0  # 10年以上

    def test_avg_salary_computation(self, monkeypatch):
        """平均薪资计算正确。"""
        import analysis.cross as cross
        monkeypatch.setattr(cross, '_get_rows', lambda: [
            (10, 20, '本科', '1-3年'),   # avg = 15
            (20, 30, '硕士', '1-3年'),   # avg = 25 -> combined avg = 20
        ])
        result = cross.salary_vs_exper()

        idx_1_3 = result['labels'].index('1-3年')
        assert result['avg_salaries'][idx_1_3] == 20.0

    def test_empty_data_all_zeros(self, monkeypatch):
        """空数据集所有值为 0。"""
        import analysis.cross as cross
        monkeypatch.setattr(cross, '_get_rows', lambda: [])
        result = cross.salary_vs_exper()

        assert sum(result['counts']) == 0
        assert all(s == 0 for s in result['avg_salaries'])

    def test_null_exper_defaults_to_不限(self, monkeypatch):
        """经验为空时归入'经验不限'。"""
        import analysis.cross as cross
        monkeypatch.setattr(cross, '_get_rows', lambda: [
            (10, 15, '本科', None),
        ])
        result = cross.salary_vs_exper()
        idx = result['labels'].index('经验不限')
        assert result['counts'][idx] == 1

    def test_salary_with_one_side_zero(self, monkeypatch):
        """只有薪资下限无上限时取下限。"""
        import analysis.cross as cross
        monkeypatch.setattr(cross, '_get_rows', lambda: [
            (15, 0, '本科', '1-3年'),
        ])
        result = cross.salary_vs_exper()
        idx = result['labels'].index('1-3年')
        assert result['avg_salaries'][idx] == 7.5  # 15/2 = 7.5


# ============================================================
# salary_vs_edu() — 薪资 vs 学历交叉统计
# ============================================================
class TestSalaryVsEdu:
    """验证按学历等级分组的薪资统计。"""

    def test_returns_correct_structure(self, monkeypatch):
        """返回结构与 salary_vs_exper 一致。"""
        import analysis.cross as cross
        monkeypatch.setattr(cross, '_get_rows', lambda: [
            (10, 15, '本科', '1-3年'),
            (20, 30, '硕士', '3-5年'),
        ])
        result = cross.salary_vs_edu()

        assert 'labels' in result and 'counts' in result and 'avg_salaries' in result
        assert len(result['labels']) == len(result['counts']) == len(result['avg_salaries'])

    def test_edu_order_preserved(self, monkeypatch):
        """学历按 不限→大专→本科→硕士→博士 排列。"""
        import analysis.cross as cross
        monkeypatch.setattr(cross, '_get_rows', lambda: [
            (1, 2, '博士', '1-3年'),
            (3, 4, '大专', '1-3年'),
            (5, 6, '不限', '经验不限'),
        ])
        result = cross.salary_vs_edu()
        assert result['labels'] == ['不限', '大专', '本科', '硕士', '博士']

    def test_fuzzy_edu_merge(self, monkeypatch):
        """'大学本科' 应被模糊归并到 '本科'。"""
        import analysis.cross as cross
        monkeypatch.setattr(cross, '_get_rows', lambda: [
            (10, 20, '大学本科', '1-3年'),
            (15, 25, '全日制本科', '1-3年'),
        ])
        result = cross.salary_vs_edu()
        idx = result['labels'].index('本科')
        assert result['counts'][idx] == 2

    def test_unknown_edu_defaults_to_不限(self, monkeypatch):
        """未知学历归入'不限'。"""
        import analysis.cross as cross
        monkeypatch.setattr(cross, '_get_rows', lambda: [
            (10, 15, '航天博士', '1-3年'),   # 应 fuzzy match 到 博士
        ])
        result = cross.salary_vs_edu()
        idx = result['labels'].index('博士')
        assert result['counts'][idx] == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
