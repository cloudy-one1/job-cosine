---
name: job-apply-direct-link
overview: 在 advice 页面的「岗位匹配推荐」和「简历审查」两个 tab 中，为每个匹配/审查的岗位卡片添加直达 51job 官网的「投递简历」按钮，按钮链接到已有的 job_url 字段。
todos:
  - id: update-agent-tools
    content: "修改 agent_tools.py: match_jobs 和 review_resume 的 SQL 查询增加 job_url 字段，for 循环解包补齐，结果字典添加 job_url"
    status: pending
  - id: update-test-fixture
    content: "修改 test_agent_tools.py 的 temp_db fixture: CREATE TABLE 增加 job_url 列，INSERT 和测试数据补齐对应字段"
    status: pending
    dependencies:
      - update-agent-tools
  - id: add-apply-buttons
    content: "修改 advice.html: TAB 3 和 TAB 4 每个岗位卡片在「查看岗位详情」旁增加「投递简历」按钮"
    status: pending
    dependencies:
      - update-agent-tools
  - id: run-tests
    content: 运行全量回归测试确保 183 条用例通过
    status: pending
    dependencies:
      - update-test-fixture
      - add-apply-buttons
---

## 用户需求

求职者在 advice 页面获取技能分析建议、完成简历优化后，希望能直接跳转到目标岗位的 51job 原始页面投递简历，形成"分析-优化-投递"的完整闭环。

## 核心功能

- 岗位匹配推荐（TAB 3）中每个匹配岗位卡片新增「投递简历」按钮，点击在新标签页打开 51job 原始职位 URL
- 简历审查（TAB 4）中每个 Gap 分析岗位卡片同样新增「投递简历」按钮
- 仅当数据库中该岗位存在 `job_url` 时显示按钮，兼容存量数据（`job_url` 为空则不显示）
- 与现有「查看岗位详情」内部链接共存，两者功能互补：一个看本站详情，一个跳外部投递

## 技术方案

### 实现策略

采用最小侵入式改动：在 agent 层补齐 `job_url` 字段的查询和返回，在模板层利用已有的 `{% if job.job_url %}` 条件渲染模式添加按钮，无需新增路由或 API。

### 修改范围

| 文件 | 改动内容 |
| --- | --- |
| `agent/agent_tools.py` | `match_jobs()` 和 `review_resume()` 的 SQL SELECT 增加 `, job_url`；for 循环解包增加变量；结果字典增加 `job_url` 字段 |
| `templates/advice.html` | TAB 3 和 TAB 4 每个岗位卡片中，在现有「查看岗位详情」链接旁增加「投递简历」按钮（`target="_blank"`） |
| `tests/test_agent_tools.py` | `temp_db` fixture 的 CREATE TABLE 增加 `job_url TEXT` 列；测试数据 INSERT 增加对应占位符 |


### 关键代码修改点

**agent_tools.py — match_jobs()**

- Line 336: `SELECT id, post, address, salary_min, salary_max, edu, exper, content` → 末尾加 `, job_url`
- Line 346: `for job_id, post, addr, smin, smax, edu_text, exper_text, content in rows:` → 末尾加 `, job_url`
- Line ~398 结果字典: 加 `'job_url': job_url or ''`

**agent_tools.py — review_resume()**

- Line 736: `SELECT id, post, address, salary_min, salary_max, edu, exper, content` → 末尾加 `, job_url`
- Line 759: `for job_id, post, addr, smin, smax, edu_text, exper_text, content in rows:` → 末尾加 `, job_url`
- Line ~832 gap_results 字典: 加 `'job_url': job_url or ''`

**advice.html — TAB 3（岗位匹配推荐）**

- 在「查看岗位详情 →」链接后新增:

```html
{% if job.job_url %}
<a href="{{ job.job_url }}" target="_blank" rel="noopener noreferrer" style="...">投递简历</a>
{% endif %}
```

**advice.html — TAB 4（简历审查）**

- 在「查看岗位详情 →」链接后同样新增投递按钮

### 兼容性保障

- `job_url or ''` 确保旧数据（NULL）不会导致模板错误
- 模板用 `{% if job.job_url %}` 条件渲染，空值不展示按钮
- `target="_blank"` + `rel="noopener noreferrer"` 符合安全最佳实践
- 测试表补充 `job_url TEXT` 列，INSERT 用 NULL 占位，不改变现有测试预期