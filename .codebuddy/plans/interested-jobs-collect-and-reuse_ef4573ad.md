---
name: interested-jobs-collect-and-reuse
overview: 为「数据展示/详情页」新增「感兴趣」收藏功能（session 存储），同一份收藏清单同时服务于求职助手的两块：简历审查针对具体岗位 JD 做 Gap 诊断，岗位匹配推荐可仅在这些收藏岗位中做六维评分（默认仍匹配全库）。
design:
  architecture:
    framework: html
  styleKeywords:
    - 蓝色科技风（数据页）
    - 暖橙卡片风（求职助手）
    - 药丸按钮
    - 收藏态高亮
    - 平滑过渡微交互
  fontSystem:
    fontFamily: Noto Sans SC
    heading:
      size: 18px
      weight: 700
    subheading:
      size: 15px
      weight: 600
    body:
      size: 14px
      weight: 400
  colorSystem:
    primary:
      - "#2563EB"
      - "#E07B4C"
    background:
      - "#FFFFFF"
      - "#FEF9F3"
    text:
      - "#1F2937"
      - "#8C7A6F"
    functional:
      - "#2563EB"
      - "#E07B4C"
      - "#38A169"
      - "#E53E3E"
todos:
  - id: add-toggle-interest-route
    content: app.py 新增 /toggle_interest 路由(CSRF+正整数校验,返回JSON)，inject_globals 加 interested_count 角标
    status: completed
  - id: extend-agent-tools-target-ids
    content: agent_tools.py 给 review_resume 与 match_jobs 增加 target_job_ids 参数，精确查询并聚焦，同步更新 TOOLS 描述
    status: completed
  - id: advice-load-interested
    content: app.py /advice 的 GET/POST 加载 session 收藏、处理 ?target_job_id 预选、向 match/review 透传 target_job_ids 并存 session
    status: completed
    dependencies:
      - add-toggle-interest-route
      - extend-agent-tools-target-ids
  - id: add-interest-buttons
    content: data.html 与 job_detail.html 增加「感兴趣」按钮与 AJAX 切换(含 csrf-token 与 stopPropagation)
    status: completed
    dependencies:
      - add-toggle-interest-route
  - id: advice-ui-interested
    content: advice.html 加 review「我感兴趣的岗位」多选清单与 match「仅在我感兴趣的岗位中匹配」勾选及结果横幅
    status: completed
    dependencies:
      - advice-load-interested
  - id: add-tests
    content: test_app_routes 与 test_agent_tools 新增 /toggle_interest、review_resume 与 match_jobs 的 target_job_ids 精准查询测试
    status: completed
    dependencies:
      - add-toggle-interest-route
      - extend-agent-tools-target-ids
---

## 用户需求

当前求职助手有两块能力：简历审查（review_resume）与岗位匹配推荐（match_jobs）。两者原本都基于「整个数据库」做泛化计算，用户认为没有针对性。需求分为两部分：

1. **简历审查**：改为针对具体岗位 JD 审查——在数据展示模块收藏「感兴趣」岗位，求职助手简历审查页从收藏清单勾选具体岗位，只对这些岗位的 JD 做 Gap 分析。
2. **岗位匹配推荐（本次扩展）**：同样要能调用收藏数据——求职助手岗位匹配页新增「仅在我感兴趣的岗位中匹配」开关，开启后 `match_jobs` 只在收藏的岗位集合内做六维匹配评分，而不是全表扫描。

## 产品概述

在数据展示模块（/data、/job）为岗位增加「感兴趣」收藏按钮，岗位 id 存入 `session['interested_jobs']`（跨页面持久，零迁移）。求职助手页的两个 tab 均可消费这份收藏：简历审查 tab 提供「我感兴趣的岗位」多选清单；岗位匹配 tab 提供「仅在我感兴趣的岗位中匹配」勾选。未使用收藏时两块功能保持原全量/城市类别兜底行为。

## 核心功能

- 数据展示页每行、岗位详情页均新增「感兴趣」收藏按钮（AJAX 切换，带收藏态高亮，不触发整行跳转）。
- 收藏岗位存入 `session['interested_jobs']`（整型 id 列表），导航栏「求职助手」旁显示收藏数量角标。
- 简历审查页：从收藏清单勾选 1 个或多个岗位，作为 `target_job_ids` 传给 `review_resume`，仅针对这些岗位 JD 做 Gap 分析与 LLM 诊断；未选则走原城市/类别兜底。
- 岗位匹配页：勾选「仅在我感兴趣的岗位中匹配」后，`match_jobs` 只在收藏岗位内做六维评分（技能/城市/学历/经验/薪资/真实性）；未勾选则全表匹配。
- 导航角标、AJAX 反馈、结果提示横幅均使用与各自页面一致的设计语言。

## 技术栈

- 后端：Flask 3.x（沿用 Jinja2 服务端渲染，无前后端分离）
- 状态存储：`session['interested_jobs']`（list[int]），与现有 `compare_state`/`match_state`/`review_state` 用法一致，零迁移
- 前端交互：原生 JS `fetch` + AJAX，复用 Flask-WTF CSRF（`csrf_token()`）
- 数据库：SQLite（`WHERE id IN (?)` 精确查询，复用 `sqlite3.connect(config.DB_PATH)` 与 WAL）

## 实现方案

### 策略

在「数据展示/详情」页通过 AJAX 调用新增的 `/toggle_interest` 路由维护 session 收藏集合。求职助手页从 session 读取收藏清单：简历审查 tab 渲染为可勾选列表，岗位匹配 tab 渲染为开关；提交时分别将收藏 id 作为 `target_job_ids` 传给 `review_resume` / `match_jobs`。两个工具函数都把 SQL 从「全量（或 LIKE 兜底）」改为「`WHERE id IN (?)` 精确命中」。

### 关键技术决策

1. **收藏用 session 而非新建表**：项目已有大量 session 状态先例，演示数据量小，避免 DDL 迁移与 WAL 复杂度，符合 YAGNI。
2. **AJAX 切换 + `event.stopPropagation()`**：`/data` 整行 `onclick` 跳转，按钮必须 stopPropagation；AJAX 返回 JSON `{interested, count}` 局部更新，避免整页刷新丢失分页位置。
3. **`target_job_ids` 作为可选参数**：`review_resume` 与 `match_jobs` 均保持向后兼容，未传时原行为完全不变，降低回归风险。
4. **岗位匹配用单一开关而非多选**：匹配本质是对「候选集」评分，用「仅在我感兴趣的岗位中匹配」开关直接复用全部收藏即可，比逐个勾选更简洁，且避免与简历审查 tab 的多选交互重复。
5. **薪资中位数随范围自适应**：`match_jobs` 的 `median_all` 由 `rows` 计算，范围精确化后中位数自然只基于命中岗位，评分基准更合理。

### 性能与可靠性

- `/toggle_interest` 仅读写 session + 返回 JSON，O(1)，无 DB 查询；CSRF 校验 + `job_id` 正整数校验（越界/非数字拒绝），防注入。
- `review_resume` / `match_jobs` 精确 `id IN (?)` 查询，命中集合通常个位，比原全表/模糊扫描更轻；`review_resume` 的 LLM 上下文仍限制前 5 个岗位控制 token 成本（沿用现有上限）。
- 深链 `/advice?tool=review&target_job_id=<id>` 预选单个岗位，与现有 `?clear_*` 模式一致。

## 实现注意事项

- `/toggle_interest` 为 POST，**必须带 CSRF token**（项目硬约束，无 token 返回 400）。`/data`、`/job` 当前模板无 CSRF token，需注入隐藏 input 并从 fetch 请求读取。
- `job_id` / `target_job_ids` 元素必须 `isdecimal()` + 正整数校验，越界返回 400，避免 SQL 注入与异常。
- `match_jobs` 构建 `IN` 子句时对占位符数量与参数一一对应，禁止字符串拼接 id。
- 不新增第三方依赖；不硬编码密钥；复用现有连接模式。
- 改动面控制在 session 读写、两个工具函数参数、三个模板、base.html 角标与两个测试文件。

## 架构设计

```mermaid
flowchart LR
    A[/data 列表页] -->|点击 感兴趣| B[/toggle_interest POST]
    C[/job 详情页] -->|点击 感兴趣| B
    B -->|toggle session['interested_jobs']| S[(Flask Session)]
    S -->|GET 读取候选清单| D[/advice 简历审查 tab]
    S -->|GET 读取收藏开关| M[/advice 岗位匹配 tab]
    D -->|勾选 target_job_ids| E[review_resume WHERE id IN]
    M -->|勾选开关 target_job_ids| F[match_jobs WHERE id IN]
    E -->|逐岗位 Gap + LLM 聚焦| R[诊断报告 + 优化简历]
    F -->|六维评分排名| MR[匹配推荐列表]
```

## 目录结构与修改点

```
project1-enhanced/
├── app.py                         # [MODIFY] 新增 /toggle_interest 路由(CSRF+正整数校验,返回JSON);
│                                  #   /advice GET 加载 session 收藏→组装候选清单+?target_job_id 预选,
│                                  #   match/review 分支读取 target_job_ids 并分别传给 match_jobs/review_resume,
│                                  #   并存 match_state/review_state; inject_globals 增加 interested_count 角标。
├── agent/agent_tools.py           # [MODIFY] review_resume 与 match_jobs 均新增 target_job_ids:list=None:
│                                  #   有值时用 WHERE id IN (?) 仅查这些岗位(匹配评分/聚焦 Gap/LLM);无值走原兜底。
│                                  #   同步更新 TOOLS['review_resume'] / TOOLS['match_jobs'] 描述。
├── templates/data.html            # [MODIFY] 表头加"感兴趣"列;行内加收藏按钮(调用 toggleInterest 并
│                                  #   stopPropagation);注入 csrf-token 隐藏域;按 session 标记已收藏态。
├── templates/job_detail.html      # [MODIFY] 操作按钮区加"感兴趣"按钮,调用同一 toggleInterest;注入 csrf-token。
├── templates/advice.html          # [MODIFY] review 表单上方加"我感兴趣的岗位"多选清单(checkbox 默认全选,
│                                  #   name=target_job_ids);match 表单加"仅在我感兴趣的岗位中匹配"勾选;
│                                  #   结果区在针对收藏时显示提示横幅。
├── templates/base.html            # [MODIFY][可选] 导航"求职助手"旁渲染 interested_count 角标。
└── tests/
    ├── test_app_routes.py         # [MODIFY] 新增 /toggle_interest 路由测试(CSRF缺失400/正常toggle增删/返回JSON)。
    └── test_agent_tools.py        # [MODIFY] 新增 review_resume 与 match_jobs 的 target_job_ids 精准查询测试。
```

## 关键代码结构

```python
# agent/agent_tools.py — 两个工具均新增可选参数
def match_jobs(skills: str = '', city: str = '', edu: str = '',
               exper: str = '', target_job_ids: list = None) -> dict:
    # target_job_ids 非空: SELECT ... FROM data WHERE id IN (?, ?, ...)
    # 否则 SELECT ... FROM data(原全表);median_all 由命中 rows 自适应计算。

def review_resume(resume_text: str, target_city: str = '',
                  target_category: str = '', target_job_ids: list = None) -> dict:
    # target_job_ids 非空: WHERE id IN (?) 精确命中,仅对这些岗位做 Gap/LLM;
    # 否则走原 city/category LIKE 兜底。
```

## 设计风格

数据展示相关页面（/data、/job）为蓝色科技风（深蓝 + 青色描边，悬停浅蓝高亮）；求职助手（/advice）为暖橙风（橙主色、药丸导航、圆角卡片）。「感兴趣」按钮在列表/详情页采用描边药丸样式，未收藏为线框、已收藏填充主题色并显示实心状态；收藏成功后有轻微缩放微交互。求职助手内的「我感兴趣的岗位」沿用暖橙卡片 + 复选框列表，与简历审查表单视觉统一；岗位匹配 tab 的「仅在我感兴趣的岗位中匹配」为带暖橙强调色的开关/复选药丸，启用时显示角标数量。结果提示横幅采用半透明暖橙渐变卡片，平滑淡入。所有按钮带 hover 过渡与微交互，符合现有动效规范。