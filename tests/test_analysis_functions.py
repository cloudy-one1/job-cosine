"""
分析层纯逻辑单元测试 — 不依赖数据库、不依赖网络。

覆盖:
  * analysis.jobtitle.classify()  — 关键词规则匹配
  * analysis.region.extract_city() — 城市提取
  * modeling.job_clustering.tokenize() — jieba 分词 + 去停用词
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ============================================================
# classify() — 职位标题分类
# ============================================================
class TestClassify:
    """验证 classify() 关键词优先匹配规则集（跨行业版）。"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from analysis.jobtitle import classify as _cls
        self.cls = _cls

    # ---- IT/软件 类（兼容旧版） ----
    def test_exact_match_backend(self):
        assert self.cls('后端开发工程师') == '后端开发'

    def test_exact_match_spider(self):
        assert self.cls('Python爬虫工程师') == '爬虫/采集'

    def test_exact_match_architect(self):
        assert self.cls('Java架构师') == '架构师'

    def test_exact_match_intern(self):
        assert self.cls('前端实习生') == '实习/应届'

    def test_exact_match_tester(self):
        assert self.cls('软件测试工程师') == '测试/质量'

    def test_exact_match_ops(self):
        assert self.cls('Linux运维工程师') == '运维/DevOps'

    def test_exact_match_web_frontend(self):
        assert self.cls('Web前端开发') == 'Web/前端'

    def test_match_senior(self):
        """关键词'测试'在规则列表中排在'高级'之前,因此先命中。"""
        assert self.cls('高级测试工程师') == '测试/质量'

    def test_senior_dev(self):
        """不含其他关键词时,'高级'命中高级/资深。"""
        assert self.cls('高级Java工程师') == '高级/资深'

    def test_case_insensitive(self):
        assert self.cls('PYTHON爬虫') == '爬虫/采集'

    def test_data_related(self):
        assert self.cls('大数据开发工程师') == '数据/AI'
        assert self.cls('数据挖掘工程师') == '数据/AI'

    def test_trigram_teacher(self):
        assert self.cls('Python培训讲师') == '培训讲师'

    def test_empty_string(self):
        assert self.cls('') == '其他岗位'

    # ---- 新增：跨行业分类 ----
    def test_accounting(self):
        assert self.cls('会计') == '财务/会计'
        assert self.cls('财务经理') == '财务/会计'
        assert self.cls('审计专员') == '财务/会计'

    def test_hr(self):
        assert self.cls('人力资源专员') == '人力资源'
        assert self.cls('招聘主管') == '人力资源'

    def test_sales(self):
        assert self.cls('销售代表') == '销售/市场'
        assert self.cls('市场专员') == '销售/市场'
        assert self.cls('客户经理') == '销售/市场'

    def test_design(self):
        assert self.cls('平面设计师') == '设计/创意'
        assert self.cls('UI设计师') == '设计/创意'

    def test_operation(self):
        assert self.cls('产品经理') == '运营/产品'
        assert self.cls('新媒体运营') == '传媒/内容'

    def test_finance(self):
        assert self.cls('金融分析师') == '金融/投资'
        assert self.cls('证券经纪人') == '金融/投资'

    def test_education(self):
        assert self.cls('英语教师') == '教育/培训'
        assert self.cls('课程顾问') == '教育/培训'

    def test_medical(self):
        assert self.cls('临床医生') == '医疗/制药'
        assert self.cls('药品研发') == '医疗/制药'

    def test_logistics(self):
        assert self.cls('物流专员') == '物流/供应链'
        assert self.cls('采购经理') == '物流/供应链'

    def test_legal(self):
        assert self.cls('律师') == '法律/法务'
        assert self.cls('法务专员') == '法律/法务'

    def test_admin(self):
        assert self.cls('行政专员') == '行政/文秘'
        assert self.cls('前台文员') == '行政/文秘'

    def test_service(self):
        assert self.cls('客服专员') == '客服/售后'
        assert self.cls('售后工程师') == '客服/售后'

    def test_media(self):
        assert self.cls('视频剪辑师') == '传媒/内容'
        assert self.cls('文案编辑') == '传媒/内容'

    def test_manufacturing(self):
        assert self.cls('生产主管') == '制造/生产'
        assert self.cls('质检员') == '制造/质检'

    def test_translation(self):
        assert self.cls('日语翻译') == '翻译/语言'

    def test_consulting(self):
        assert self.cls('管理咨询顾问') == '咨询/顾问'

    def test_engineering(self):
        assert self.cls('土木工程师') == '建筑/工程'

    def test_fallback_unknown(self):
        """完全无法分类的回退到'其他岗位'。"""
        # '资深' 也会命中 RULES → '高级/资深',用真正无法分类的标题测试
        assert self.cls('首席幸福官') == '其他岗位'


# ============================================================
# extract_city() — 城市提取
# ============================================================
class TestExtractCity:
    """验证从地址字符串中提取城市名。"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from analysis.region import extract_city as _ec
        self.ec = _ec

    def test_standard_address(self):
        assert self.ec('北京-海淀区') == '北京'

    def test_address_with_multi_dash(self):
        assert self.ec('上海-浦东新区-张江') == '上海'

    def test_no_dash(self):
        assert self.ec('深圳') == '深圳'

    def test_empty(self):
        assert self.ec('') == 'Unknown'

    def test_none(self):
        assert self.ec(None) == 'Unknown'

    def test_english_city(self):
        assert self.ec('Remote-Anywhere') == 'Remote'


# ============================================================
# tokenize() — jieba 分词 + 去停用词
# ============================================================
class TestTokenize:
    """验证 jieba 分词正确过滤无意义高频词和标点。"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from modeling.job_clustering import tokenize as _tok
        self.tok = _tok

    def test_removes_stopwords(self):
        words = self.tok('Python工程师开发')
        # 'python' and '工程师' and '开发' are stopwords
        assert 'python' not in words
        assert '工程师' not in words
        assert '开发' not in words

    def test_keeps_meaningful(self):
        words = self.tok('高级Java后端')
        # "java" and "后端" and "高级" may be meaningful depending on stopword list
        assert len(words) > 0

    def test_empty_input(self):
        assert self.tok('') == []

    def test_punct_removed(self):
        """纯标点应全部被过滤。"""
        words = self.tok('()/（）、')
        assert words == []

    def test_lowercase_applied(self):
        """Python → python, 然后被停用词过滤。"""
        words = self.tok('Python')
        assert 'python' not in words

    def test_space_handling(self):
        words = self.tok('  测试   ')
        assert '测试' in words




if __name__ == '__main__':
    pytest.main([__file__, '-v'])
