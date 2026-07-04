"""
Agent 工具函数单元测试 — compare_jobs 和 extract_skills。

使用临时 SQLite 数据库注入,不依赖真实 data.db。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import tempfile
import sqlite3


@pytest.fixture
def temp_db(monkeypatch):
    """创建含测试数据的临时 SQLite 数据库，注入到 agent_tools 中。"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS data (
            post TEXT, address TEXT, salary_min REAL, salary_max REAL,
            edu TEXT, exper TEXT, content TEXT DEFAULT ''
        )
    """)
    test_data = [
        ('Python后端开发', '北京-海淀区', 15, 25, '本科', '3-5年'),
        ('Java后端开发', '北京-朝阳区', 12, 20, '本科', '1-3年'),
        ('Python后端开发', '上海-浦东新区', 18, 30, '硕士', '3-5年'),
        ('前端开发工程师', '上海-徐汇区', 10, 18, '大专', '1-3年'),
        ('数据爬虫工程师', '北京-海淀区', 12, 22, '本科', '1-3年'),
        ('Python爬虫工程师', '深圳-南山区', 15, 25, '本科', '3-5年'),
        ('Java后端开发', '上海-浦东新区', 15, 25, '本科', '3-5年'),
        ('运维工程师', '深圳-福田区', 8, 15, '大专', '经验不限'),
        ('测试工程师', '上海-静安区', 10, 18, '本科', '1-3年'),
        ('Web前端开发', '北京-海淀区', 12, 22, '本科', '3-5年'),
    ]
    conn.executemany(
        "INSERT INTO data (post, address, salary_min, salary_max, edu, exper) VALUES (?,?,?,?,?,?)",
        test_data
    )
    conn.commit()
    conn.close()

    import config
    monkeypatch.setattr(config, 'DB_PATH', path)

    # 强制 agent_tools 的 _connect 使用新路径 (config.DB_PATH 在 _connect 调用时解析)
    from agent import agent_tools
    # 无需特殊处理: _connect() 内部是 sqlite3.connect(config.DB_PATH),monkeypatch 后生效

    yield path
    os.unlink(path)


# ============================================================
# compare_jobs — 城市/类别并排对比
# ============================================================
class TestCompareJobs:
    """验证 compare_jobs 两种对比模式。"""

    def test_city_compare_structure(self, temp_db):
        """按城市对比返回正确结构。"""
        from agent.agent_tools import compare_jobs
        result = compare_jobs('city', '北京', '上海')

        assert result['compare_type'] == 'city'
        assert 'a' in result and 'b' in result
        # 北京: 4 条 (Python后端×1, Java后端×1, 爬虫×1, Web前端×1)
        assert result['a']['value'] == '北京'
        assert result['a']['count'] == 4
        assert result['a']['avg_salary_k'] > 0
        assert len(result['a']['top_edu']) > 0
        assert len(result['a']['top_exper']) > 0
        # 上海: 4 条 (Python后端×1, 前端×1, Java后端×1, 测试×1)
        assert result['b']['value'] == '上海'
        assert result['b']['count'] == 4

    def test_category_compare_structure(self, temp_db):
        """按职位类别对比返回正确结构。"""
        from agent.agent_tools import compare_jobs
        result = compare_jobs('category', '后端开发', 'Web开发')

        assert result['compare_type'] == 'category'
        assert result['a']['value'] == '后端开发'
        assert result['a']['count'] > 0
        assert result['b']['value'] == 'Web开发'
        assert result['b']['count'] >= 0  # 可能为 0

    def test_unknown_city_returns_zero_count(self, temp_db):
        """不存在的城市返回 0 计数。"""
        from agent.agent_tools import compare_jobs
        result = compare_jobs('city', '拉萨', '乌鲁木齐')

        assert result['a']['count'] == 0
        assert result['a']['avg_salary_k'] == 0
        assert result['b']['count'] == 0

    def test_unknown_category_returns_zero_count(self, temp_db):
        """不存在的类别返回 0 计数。"""
        from agent.agent_tools import compare_jobs
        result = compare_jobs('category', '培训讲师', '运营')

        assert result['a']['count'] == 0

    def test_same_city_both_sides(self, temp_db):
        """同城市对比两侧都应有数据。"""
        from agent.agent_tools import compare_jobs
        result = compare_jobs('city', '上海', '上海')
        assert result['a']['count'] == result['b']['count']
        assert result['a']['avg_salary_k'] == result['b']['avg_salary_k']


# ============================================================
# extract_skills — 技能关键词提取
# ============================================================
class TestExtractSkills:
    """验证 extract_skills 分词+停用词+top_n。"""

    def test_returns_skills_list(self, temp_db):
        """从全部职位提取技能,返回正确结构。"""
        from agent.agent_tools import extract_skills
        result = extract_skills(keyword='', top_n=10)

        assert result['keyword'] == '全部'
        assert result['total_jobs'] == 10
        assert isinstance(result['skills'], list)
        assert len(result['skills']) > 0
        assert len(result['skills']) <= 10
        for s in result['skills']:
            assert 'skill' in s and 'count' in s
            assert s['count'] > 0
            # 停用词不应出现
            assert s['skill'] not in ('工程师', '开发')

    def test_keyword_filter_works(self, temp_db):
        """关键词筛选应只处理匹配的职位标题。"""
        from agent.agent_tools import extract_skills
        result = extract_skills(keyword='爬虫', top_n=15)

        assert result['keyword'] == '爬虫'
        assert result['total_jobs'] == 2  # 数据爬虫工程师, Python爬虫工程师
        assert isinstance(result['skills'], list)

    def test_top_n_limits_result(self, temp_db):
        """top_n 参数限制返回数量。"""
        from agent.agent_tools import extract_skills
        result = extract_skills(keyword='', top_n=3)
        assert len(result['skills']) <= 3

    def test_no_match_returns_empty(self, temp_db):
        """无匹配职位时返回空列表+提示信息。"""
        from agent.agent_tools import extract_skills
        result = extract_skills(keyword='产品经理工资上涨', top_n=10)

        assert result['skills'] == []
        assert 'message' in result
        assert result['total_jobs'] == 0

    def test_top_n_defaults_to_15(self, temp_db):
        """不传 top_n 时默认 15。"""
        from agent.agent_tools import extract_skills
        result = extract_skills()
        assert len(result['skills']) <= 15

    def test_stop_words_are_excluded(self, temp_db):
        """停用词列表中的词不应出现。"""
        from agent.agent_tools import extract_skills
        result = extract_skills(keyword='', top_n=20)

        for s in result['skills']:
            assert s['skill'] not in ('五险一金', '周末双休', '绩效奖金', '的', '了')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
