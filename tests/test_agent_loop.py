"""
agent_core 单次调用 Agent 的集成测试。

v2 变更: 移除 ReAct 循环和 Critic 审计，改为预加载数据 + 单次 LLM 调用。
测试用确定性假 LLM 验证 agent 预加载了 overview 数据并返回预期结果。
"""
import json
from agent.agent_core import run_agent

fake_output = (
    '## 📊 基于数据库分析（来自本地招聘数据）\n\n'
    '在本数据库的 100 条岗位中，后端开发占比最高...\n\n'
    '## 💡 普适性建议（行业通用分析，非数据库推导）\n\n'
    '以下建议基于行业通用认知...\n'
    '- 持续学习云原生技术\n'
    '- 关注 AI 辅助开发趋势'
)

fake_output_no_sections = (
    '根据数据库数据,当前共有 100 条岗位,主要分布在北京、上海。'
    '薪资中位数约 1.5万/月。'
)


def fake_llm_no_keyword(messages):
    """假 LLM: 验证 system prompt 包含了预加载的数据。"""
    system = messages[0]['content']
    # 验证 system prompt 包含预加载数据
    assert '"total_jobs"' in system, 'system prompt 应包含 total_jobs'
    assert 'category_distribution' in system, 'system prompt 应包含 category_distribution'
    assert 'city_distribution' in system, 'system prompt 应包含 city_distribution'
    assert 'PRE-LOADED DATA' in system, 'system prompt 应标明数据预加载'
    return fake_output


def fake_llm_with_keyword(messages):
    """假 LLM: 验证关键词预查询也包含了。"""
    system = messages[0]['content']
    assert 'keyword_query' in system, 'system prompt 应包含 keyword_query'
    assert 'Python' in system, 'system prompt 应包含关键词'
    return fake_output


def fake_llm_no_sections(messages):
    """假 LLM: 输出无 ## 标题的答案，验证 _extract_answer_text 不回退到空。"""
    return fake_output_no_sections


# ============================================================
# 测试
# ============================================================
class TestRunAgentV2:
    """验证新版 run_agent: 预加载 + 单次调用。"""

    def test_run_agent_returns_answer_and_context(self, monkeypatch):
        """run_agent 返回 (answer, data_context)，不返回 trace。"""
        monkeypatch.setattr('agent.agent_core.call_llm_with_fallback',
                            lambda messages, **kw: (fake_output, 'test'))
        answer, ctx = run_agent('Python 后端开发', api_key='fake-key')
        assert isinstance(answer, str)
        assert '基于数据库分析' in answer
        assert isinstance(ctx, dict)
        assert 'total_jobs' in ctx
        assert 'city_distribution' in ctx

    def test_run_agent_data_context_has_required_keys(self, monkeypatch):
        """data_context 包含所有必需的 overview 键。"""
        monkeypatch.setattr('agent.agent_core.call_llm_with_fallback',
                            lambda messages, **kw: (fake_output, 'test'))
        _, ctx = run_agent('测试问题', api_key='fake-key')
        for key in ['total_jobs', 'category_distribution', 'city_distribution',
                     'edu_distribution', 'exper_distribution']:
            assert key in ctx, f'data_context 缺少键: {key}'

    def test_run_agent_keyword_extraction(self, monkeypatch):
        """问题中包含技术关键词时，data_context 应有 keyword_query。"""
        monkeypatch.setattr('agent.agent_core.call_llm_with_fallback',
                            lambda messages, **kw: (fake_output, 'test'))
        _, ctx = run_agent('想了解 Python Django 开发', api_key='fake-key')
        assert 'keyword_query' in ctx, '应提取到 Python 关键词'
        assert ctx['keyword_query']['keyword'] == 'Python'

    def test_run_agent_no_keyword_in_question(self, monkeypatch):
        """问题中无技术关键词时，data_context 不含 keyword_query。"""
        monkeypatch.setattr('agent.agent_core.call_llm_with_fallback',
                            lambda messages, **kw: (fake_output, 'test'))
        _, ctx = run_agent('就业前景如何', api_key='fake-key')
        assert 'keyword_query' not in ctx, '无技术关键词不应有 keyword_query'

    def test_run_agent_answer_extraction_no_sections(self, monkeypatch):
        """LLM 输出无 Markdown 标题时，原样返回（不回退到空）。"""
        monkeypatch.setattr('agent.agent_core.call_llm_with_fallback',
                            lambda messages, **kw: (fake_output_no_sections, 'test'))
        answer, _ = run_agent('测试', api_key='fake-key')
        assert len(answer) > 0
        assert '100 条岗位' in answer

    def test_run_agent_with_custom_llm_call(self, monkeypatch):
        """llm_call 钩子正常工作。"""
        answer, ctx = run_agent(
            '随便问', api_key='fake-key',
            llm_call=lambda msgs: fake_output
        )
        assert '基于数据库分析' in answer
        assert 'total_jobs' in ctx

    def test_run_agent_data_context_total_matches_sum(self, monkeypatch):
        """total_jobs 应等于各分类 count 之和。"""
        monkeypatch.setattr('agent.agent_core.call_llm_with_fallback',
                            lambda messages, **kw: (fake_output, 'test'))
        _, ctx = run_agent('测试', api_key='fake-key')
        total = sum(c['count'] for c in ctx['category_distribution'])
        assert ctx['total_jobs'] == total


if __name__ == '__main__':
    import pytest
    import sys
    sys.exit(pytest.main([__file__, '-v', '--tb=short']))
