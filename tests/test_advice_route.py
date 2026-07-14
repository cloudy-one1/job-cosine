"""
Flask /advice 路由单元测试 — 覆盖 3-tab 功能（综合Agent、城市对比、岗位匹配）。

使用 Flask test_client 发送请求，不启动真实服务器。
测试态下关闭 CSRF，单独验证 CSRF token 存在性。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import tempfile
import sqlite3


@pytest.fixture
def client():
    """构造 Flask 应用测试客户端（CSRF 关闭）。"""
    from app import app
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as c:
        yield c


@pytest.fixture
def temp_db(monkeypatch):
    """创建含测试数据的临时数据库，注入到 config.DB_PATH。"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post TEXT, address TEXT, salary_min REAL, salary_max REAL,
            edu TEXT, exper TEXT, content TEXT DEFAULT '', job_url TEXT
        )
    """)
    test_data = [
        ('Python后端开发工程师', '北京-海淀区', 15, 25, '本科', '3-5年'),
        ('Java后端开发工程师', '上海-浦东新区', 12, 20, '本科', '1-3年'),
        ('Python爬虫工程师', '深圳-南山区', 15, 25, '本科', '3-5年'),
        ('Web前端开发工程师', '北京-朝阳区', 10, 18, '本科', '1-3年'),
        ('数据分析师', '上海-徐汇区', 12, 22, '硕士', '3-5年'),
    ]
    conn.executemany(
        "INSERT INTO data (post, address, salary_min, salary_max, edu, exper) VALUES (?,?,?,?,?,?)",
        test_data
    )
    conn.commit()
    conn.close()

    import config
    monkeypatch.setattr(config, 'DB_PATH', path)

    yield path
    os.unlink(path)


# ============================================================
# GET 请求 — 两个 tab 页面渲染
# ============================================================
class TestAdviceGetTabs:
    """验证 GET /advice 及 ?tool= 参数能正确渲染两个 tab。"""

    def test_get_default_agent_tab(self, client):
        """GET /advice 默认渲染 Agent 页面，包含两个 tab 按钮。"""
        resp = client.get('/advice')
        assert resp.status_code == 200
        text = resp.data.decode('utf-8')
        assert '普适性建议' in text
        assert '城市对比' in text
        # 确认 CSRF token 存在于表单中
        assert 'csrf_token' in text

    def test_get_compare_tab(self, client):
        """GET /advice?tool=compare 渲染对比 tab。"""
        resp = client.get('/advice?tool=compare')
        assert resp.status_code == 200
        text = resp.data.decode('utf-8')
        assert '城市 A' in text
        assert '城市 B' in text

    def test_get_invalid_tool_fallbacks_to_agent(self, client):
        """GET /advice?tool=unknown 回退到 Agent tab。"""
        resp = client.get('/advice?tool=unknown')
        assert resp.status_code == 200
        text = resp.data.decode('utf-8')
        assert '普适性建议' in text


# ============================================================
# POST 请求 — 综合 Agent 模式
# ============================================================
class TestAdvicePostAgent:
    """验证 POST /advice tool=agent 的完整流程。"""

    def test_post_agent_empty_question_shows_error(self, client):
        """question 为空时返回提示。"""
        resp = client.post('/advice', data={'tool': 'agent', 'question': ''})
        assert resp.status_code == 200
        assert '请输入你的问题' in resp.data.decode('utf-8')

    def test_post_agent_no_api_key_shows_error(self, client, monkeypatch):
        """有 question 但无 API Key 时返回提示。"""
        import config
        monkeypatch.setattr(config, 'DEEPSEEK_API_KEY', '')
        monkeypatch.setattr(config, 'QWEN_API_KEY', '')
        resp = client.post('/advice', data={
            'tool': 'agent',
            'question': 'Python 爬虫就业',
        })
        assert resp.status_code == 200
        assert 'DEEPSEEK_API_KEY' in resp.data.decode('utf-8')

    def test_post_agent_with_api_key(self, client, monkeypatch):
        """有 API Key 时调用 run_agent，mock 返回结果。"""
        import config
        monkeypatch.setattr(config, 'DEEPSEEK_API_KEY', 'fake-test-key')
        monkeypatch.setattr(config, 'QWEN_API_KEY', '')

        # Mock run_agent 避免真实调用 LLM（新签名返回 (answer, data_context)）
        import agent.agent_core as agent_core
        monkeypatch.setattr(
            agent_core, 'run_agent',
            lambda question, **kwargs: (
                f'关于 {question} 的测试回答',
                {'total_jobs': 5, 'city_distribution': [], 'category_distribution': [],
                 'edu_distribution': [], 'exper_distribution': []}
            )
        )

        resp = client.post('/advice', data={
            'tool': 'agent',
            'question': 'Python爬虫',
        })
        assert resp.status_code == 200
        text = resp.data.decode('utf-8')
        assert '关于 Python爬虫 的测试回答' in text


# ============================================================
# POST 请求 — 城市对比模式
# ============================================================
class TestAdvicePostCompare:
    """验证 POST /advice tool=compare 的城市对比功能。"""

    def test_post_compare_empty_input_shows_error(self, client):
        """城市为空时返回提示。"""
        resp = client.post('/advice', data={
            'tool': 'compare',
            'a': '',
            'b': '',
        })
        assert resp.status_code == 200
        assert '请输入两个要对比' in resp.data.decode('utf-8')

    def test_post_compare_city_with_data(self, client, temp_db):
        """有数据时返回城市对比结果。"""
        resp = client.post('/advice', data={
            'tool': 'compare',
            'a': '北京',
            'b': '上海',
        })
        assert resp.status_code == 200
        text = resp.data.decode('utf-8')
        assert '城市 A' in text
        assert '城市 B' in text
        assert '北京' in text
        assert '上海' in text


# ============================================================
# 边界与回退
# ============================================================
class TestAdviceEdgeCases:
    """边界场景验证。"""

    def test_post_unknown_tool_fallback(self, client):
        """未知 tool 类型回退并显示错误。"""
        resp = client.post('/advice', data={'tool': 'nonexistent'})
        assert resp.status_code == 200
        assert '未知工具类型' in resp.data.decode('utf-8')

    def test_csrf_token_present_in_all_forms(self, client):
        """两个 tab 的表单中都包含 csrf_token 隐藏字段。"""
        resp = client.get('/advice')
        text = resp.data.decode('utf-8')
        # 数 csrf_token 出现的次数（两个表单各一个）
        count = text.count('csrf_token')
        assert count >= 2, f'预期至少 2 个 csrf_token，实际 {count}'

    def test_data_tab_attribute_present(self, client):
        """tab 按钮使用 data-tab 属性（JS 切换依赖）。"""
        resp = client.get('/advice')
        text = resp.data.decode('utf-8')
        assert 'data-tab="agent"' in text
        assert 'data-tab="compare"' in text
