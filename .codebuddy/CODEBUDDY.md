# CODEBUDDY.md — 项目唯一真相来源

> 本文件是 CodeBuddy 的项目上下文。包含项目架构、开发规范、坑点记录、以及 CodeBuddy 专属的会话信息。
> **所有关于本项目的信息都在这里，不再需要额外读 ARCHITECTURE.md。**

---

## 1. 项目概述

- **项目名称**：job-cosine
- **项目性质**：毕业设计 / 求职数据分析平台
- **一句话描述**：采集招聘网站（目前 51job）Python 岗位数据 → 清洗入库 → 多维度分析（薪资、学历、经验、地区、技能） → 聚类建模 + 薪资预测 → AI Agent 给出求职建议，并用 Flask 网页端全部展示。
- **远程仓库**：`https://github.com/cloudy-one1/job-cosine.git`
- **答辩演示分支**：`main`（受保护，禁止直接 push，必须走 PR 合并）
- **日常开发分支**：`develop`（新对话默认在 develop 上写代码）

---

## 2. 技术栈（全部已落地）

| 层级 | 选型 | 说明 |
|---|---|---|
| 后端 Web | **Flask 3.x** | 纯服务端渲染（Jinja2 模板），无前后端分离 |
| 安全 | **Flask-WTF 1.x** + **Flask-Limiter 3.x** | CSRF 全表单保护；`/collect` 限流 5 次/小时；可选 `COLLECT_TOKEN` 口令保护采集 |
| 数据库 | **SQLite 3（文件型 data.db）** | 开启 WAL 模式提高并发；项目根目录即数据文件 |
| 数据采集 | **Playwright + playwright-stealth** | requests 库被 51job WAF 拦截，必须用无头浏览器 + 隐身插件绕过 |
| 数据分析 | **pandas + numpy** | 薪资分段解析、经验/学历/地区聚合 |
| NLP | **jieba** | 岗位描述/技能词中文分词与词频 |
| 机器学习 | **scikit-learn 1.x + joblib** | KMeans 岗位聚类 + 线性回归/随机森林薪资预测(三模型对比);模型结果缓存避免重复训练 |
| AI Agent | 自研轻量 Agent + **DeepSeek API** | 基于采集数据+模型结果，输出个性化求职建议；密钥从 `.env` 读 |
| 部署 | **Docker + docker-compose** | 容器内只跑 Web + ML + Agent，Playwright 爬虫在宿主机运行（体积原因）；volume 挂载 `data.db` + 源码热更新 |
| 测试 | **pytest 7.x** | 全部测试在 `tests/` 目录，总计 160 个用例，覆盖率 > 90% |
| 启动方式 | `python app.py`（venv 本机）或 `docker compose up -d` | Debug 开关由根目录 `.debug` 文件存在与否决定（不是 FLASK_DEBUG 环境变量） |

---

## 3. 项目结构（四层架构，硬约束，**严禁改动分工**）

```
project1/
├── CODEBUDDY.md             ← 你现在读的这个（唯一真相来源）
├── README.md                ← 给人看的文档（GitHub 展示）
├── app.py                   ← Flask 入口；路由 + CSRF + 限流 + 启动逻辑
├── config.py                ← 全局常量导出：DB_PATH / DB_URI / DEEPSEEK_API_KEY / COLLECT_TOKEN
├── requirements.txt         ← Python 依赖
├── .env.example             ← 环境变量模板（复制为 .env 后填真实值，.env 已被 gitignore）
├── .debug                   ← （可选）存在即开启 Flask Debug 模式，优先级覆盖 FLASK_DEBUG 环境变量
├── data.db                  ← SQLite 数据库（gitignore，由爬虫脚本本地生成）
│
│  # ===== 以下 4 个模块是硬约束的四层架构，名字和职责不能变 =====
│
├── data/                    ← 第 1 层：数据采集与清洗
│   ├── python_job_scraper.py   ← Playwright 爬虫（51job Python 岗位）
│   ├── salary_parser.py        ← 薪资字符串解析（"1.5-2万/月" → 数值化）
│   └── fix_duplicate_address.py← 地址去重脚本
│
├── analysis/                ← 第 2 层：统计分析（输出图表所需数据）
│   ├── xueli.py               ← 学历分布统计
│   ├── jinyan.py              ← 经验分布统计
│   ├── xinzi.py               ← 薪资分段统计
│   ├── region.py              ← 地区分布统计
│   ├── cross.py               ← 交叉分析(薪资 vs 经验/学历)
│   └── jobtitle.py            ← 职位名称关键词 + 技能词频（jieba）
│
├── modeling/                ← 第 3 层：机器学习建模
│   ├── salary_predict.py      ← 薪资预测模型（训练+预测）
│   ├── job_clustering.py      ← 岗位聚类（KMeans 技能向量）
│   └── cache.py               ← 模型结果缓存（避免每次请求重训，sklearn/jieba 懒加载提速启动）
│
├── agent/                   ← 第 4 层：AI Agent 求职建议
│   ├── agent_core.py          ← Agent 主循环 + 工具调用调度（参数白名单用 inspect.signature）
│   └── agent_tools.py         ← Agent 可用的工具函数（查数据/查模型/查词频等）
│
├── templates/               ← Flask Jinja2 模板（所有页面）
│   ├── base.html              ← 基础模板（导航栏 + 公共头尾）
│   ├── input.html             ← 首页：输入城市/关键词/薪资期望（带 CSRF token）
│   ├── data.html              ← 数据总览页（分页展示采集到的职位列表）
│   ├── h.html                 ← 分析图表页（ECharts：饼图/柱状图/地图）
│   ├── ml.html                ← 建模结果页（聚类簇 + 薪资预测表单+结果）
│   ├── advice.html            ← Agent 求职建议页（带 CSRF token 提交画像）
│   └── collect.html           ← 数据采集管理页（可选 COLLECT_TOKEN 口令校验）
│
├── tests/                   ← 全部单元/集成测试（必过）
│   ├── test_app_routes.py      ← 路由/安全/CSRF/限流/分页输入校验回归测试
│   ├── test_analysis_functions.py
│   ├── test_model_logic.py
│   ├── test_agent_tools.py     ← Agent 工具函数测试 (compare_jobs / extract_skills)
│   ├── test_cross.py           ← 交叉分析函数测试 (salary_vs_exper / salary_vs_edu)
│   ├── test_salary_parser.py
│   ├── test_python_job_scraper.py
│   └── test_agent_loop.py
│
├── Dockerfile               ← 容器镜像（Python 3.11-slim，只装 Playwright Python 绑定，不下 Chromium）
├── docker-compose.yml       ← 开发部署：5000:5000，挂载 data.db / templates / app.py / config.py 热更新
├── .dockerignore
└── .gitignore               ← 已排除 .env / .debug / data.db / __pycache__ / node_modules/ / venv/
```

---

## 4. 核心配置文件与修改位置

| 你想改什么 | 改哪个文件 |
|---|---|
| API 密钥、采集口令、Debug 开关、Flask host/port | 根目录 `.env`（没有就 `cp .env.example .env` 填值） |
| 新增全局配置常量（如新数据库路径） | `config.py` |
| Python 依赖增删 | `requirements.txt`，改完 `pip install -r requirements.txt` |
| Docker 端口映射 / Volume 挂载 / 环境变量 | `docker-compose.yml`（推荐）或 `Dockerfile`（构建层改动） |
| Flask 启动逻辑、Debug 判定、路由加限流 | `app.py` |
| 路由对应的页面 HTML / 图表 / 表单 | `templates/*.html` |
| Agent 可用的工具函数 / 参数白名单 | `agent/agent_core.py` + `agent/agent_tools.py` |
| Git 忽略规则（不想提交的文件） | `.gitignore` |

### 关键配置常量（导出自 `config.py`）

```python
DB_PATH          # SQLite data.db 的绝对路径（= 项目根目录）
DB_URI           # SQLAlchemy 格式：sqlite:/// + DB_PATH
DEEPSEEK_API_KEY # Agent 用的密钥（.env > 系统环境变量 > 空串）
COLLECT_TOKEN    # /collect 采集路由保护口令，空则不启用
```

### Flask 启动机制（在 `app.py` 末尾）

- Debug 判定：根目录存在 `.debug` 文件 → 开 Debug + 开 `use_reloader`
- 否则：关 Debug，关 reloader（**必须关 reloader**，否则 Playwright 长任务会被双进程打断）
- Host 默认：`127.0.0.1`（`FLASK_HOST` 改）
- Port 默认：`5000`（`FLASK_PORT` 改）

---

## 5. Git 规范（硬约束，**必须遵守**）

### 5.1 分支策略

```
main                ← 稳定分支（答辩演示用），✅ GitHub 已设置保护：
                        · 合并必须走 PR（不能直接 push）
                        · 对管理员（你）也生效（防止手抖）
  ↑ PR 合并（develop → main）
  |
develop             ← 日常开发主力分支（当前默认工作分支）
  ↑ merge
  |
feature/xxx         ← 可选：大功能临时分支（比如 feature/crawler-v2），用完即删
fix/xxx             ← 可选：Bug 修复临时分支
hotfix/xxx          ← 可选：main 上紧急问题修复
```

- 新开对话默认 **checkout develop**，不要在 main 上写代码
- 答辩/阶段性成果合并一次 main，保证 main 永远是「可展示版本」

### 5.2 Commit Message 格式（type: description）

```
feat: 新增薪资预测表单提交逻辑
fix: 关闭 Flask reloader 避免 Playwright 任务被双进程打断
docs: 同步 README 测试用例数量 + 更新 Debug 开关说明
refactor: 分析模块 xueli 与 jinyan 抽出公共聚合函数
test: 新增 /data 分页越界参数回归测试
perf: sklearn jieba 懒加载，Flask 启动从 6s → 0.5s
chore: .gitignore 新增 .qoder/ 排除 Trae 知识库缓存
security: 加 CSRF 保护全表单 + /collect 限流 5/h + COLLECT_TOKEN
```

### 5.3 远程仓库 URL 注意 ⚠️

- 仓库名是 **`job-cosine`**（不带末尾点，2026-07-03 已从带点名改名）
- 当前标准 Remote URL：`https://github.com/cloudy-one1/job-cosine.git`
- 如果 push 报 `repository not found` 或出现 `This repository moved` 警告，99% 是 remote URL 还是旧名（末尾带点），执行修正：
  ```bash
  git remote set-url origin https://github.com/cloudy-one1/job-cosine.git
  ```

---

## 6. 安全约定（上一轮已加固，**禁止回退**）

| 约定 | 说明 |
|---|---|
| 🔑 密钥永不硬编码 | `DEEPSEEK_API_KEY` 等全部走 `.env`（已加入 gitignore），代码里只从 `os.environ` / `config.py` 读 |
| 🔑 Flask Secret | session/CSRF 签名用 `FLASK_SECRET` 环境变量；不设则每次启动随机（仅开发 OK），容器/多进程/重启后**必须设固定 64 位随机串** |
| 🛡️ CSRF 全表单 | 所有 POST 表单（input / advice / collect）都有 `{{ form.hidden_tag() }}`（Flask-WTF）。新增 POST 页面必须加，不加会 400 |
| 🛡️ 接口限流 | Flask-Limiter 默认 `/collect` 限 5 次/小时（防误触发清数据），新增昂贵接口要加 |
| 🛡️ 采集口令 | `.env` 设 `COLLECT_TOKEN` 非空时，`/collect` POST 必须带同值 token 字段，templates/input.html 条件渲染输入框 |
| 🛡️ 输入白名单 | `/data` 分页 `page` 参数必须是正整数，越界/非数字返回 400 不崩；Agent 工具函数参数用 `inspect.signature` 白名单校验，不允许任意传参 |
| 🛡️ SQLite 并发 | 所有 DB 连接开启 WAL：`PRAGMA journal_mode=WAL;`，防写入时读阻塞 |
| 🚫 默认关 Debug | 公网部署绝不允许开 Debug，更不能 host=0.0.0.0 同时开 Debug（Werkzeug RCE 风险） |

---

## 7. 常见坑 & 已验证解决方案

### 坑 1：requests 爬 51job 拿不到数据 / 返回 WAF 页面
- **原因**：51job 反爬升级，传统 requests 必拦截
- **解决方案**：必须用 `Playwright + playwright-stealth`，启动参数 `headless=True`，每请求间隔 2-4 秒随机 sleep

### 坑 2：Flask 启动后 Playwright 任务跑了一半就中断 / 打印两次
- **原因**：Debug 模式默认开 `use_reloader=True`，主进程 + 重载子进程各跑一遍
- **解决方案**：根目录没 `.debug` 文件就强制 `use_reloader=False`（`app.py` 已写）。调试想 reloader 就 `touch .debug`，跑完删了

### 坑 3：模板改了浏览器刷新没变化
- **原因**：多进程占了 5000 端口（两个 venv Flask + 一个 Docker 容器同时跑），浏览器命中旧进程
- **解决方案**：
  ```powershell
  # Windows PowerShell 查 5000 谁占着
  Get-NetTCPConnection -LocalPort 5000 | Select-Object OwningProcess
  # 杀掉对应 PID 或 docker compose down，再启一个 Flask
  ```

### 坑 4：h.html 学历占比 / 经验占比是环状图（Donut）不是饼图（Pie）
- **原因**：ECharts `series[].radius = ['45%', '72%']` 就是环，改 `radius = ['0%', '70%']` 才是实心饼
- **解决方案**：已改，但遇到图表显示异常时优先查端口是否跑旧进程（见坑 3）

### 坑 5：第一次启动 Flask 卡死/超 10s 才就绪
- **原因**：`import sklearn / jieba / pandas` 特别慢，VSCode 终端误判死锁
- **解决方案**：已在 `modeling/cache.py` 做懒加载 + 3 段进度打印，启动≈0.5s。如果又慢了，查是不是新增了顶层 import 大库

### 坑 6：分页参数 /data?page=abc 导致 500
- **原因**：未校验输入类型，直接 `int(page)` 抛 ValueError
- **解决方案**：`tests/test_app_routes.py` 有回归测试；`app.py` 所有 URL 数值参数统一做 `isdecimal()` + 正整数校验，越界→400

### 坑 7：Push 到 GitHub 报 `repository not found` 或 `This repository moved`
- **原因**：仓库曾用名是 `job-cosine.`（末尾带点），2026-07-03 已改为 `job-cosine`（不带点）；旧 URL 仍有重定向但每次都有警告，长期会失效
- **解决方案**：统一把本地 remote 更新为新 URL：
  ```bash
  git remote set-url origin https://github.com/cloudy-one1/job-cosine.git
  ```

---

## 8. 常用命令速查

```bash
# ===== 开发运行 =====
python app.py                            # 本机 venv 跑（开发）
# 想临时开 Debug+reloader：在项目根创建空文件 .debug 即可，删了就关

# ===== 容器运行 =====
docker compose up -d --build             # 首次 / 更新依赖后构建并后台运行
docker compose down                      # 停容器
docker compose logs -f                   # 看实时日志

# ===== 测试 =====
pytest tests/ -v --tb=short              # 跑所有测试（必须全绿才能合并 main）
pytest tests/test_app_routes.py -v       # 只跑安全/路由回归测试（改 app.py 后必跑）

# ===== Git 常用 =====
git status                               # 永远先看当前在哪个分支、有没有未提交
git checkout develop                     # 回开发分支
git add . && git commit -m "type: 描述"  # 提交
git push                                 # develop 直接推
# 合并 main 流程（GitHub 网页端做 PR）：
#   git checkout main && git pull
#   去 github 开 develop → main 的 PR
#   确认无冲突 → Merge pull request
#   git checkout develop
```

---

## 9. AI 行为硬约束（Agent 行为准则）

1. **禁止直接在 main 分支改代码**。任何修改前先 `git status` 确认当前在 develop，不在就先 checkout。
2. **新增 POST 路由/表单必须加 CSRF**。Flask-WTF，模板写 `{{ form.hidden_tag() }}`。
3. **密钥/Token 绝对不能写进任何代码文件**。一律走 `.env` + `config.py` 常量。
4. **改完 app.py / 安全逻辑必须跑 `pytest tests/test_app_routes.py -v`**。改分析/模型跑对应测试。全部通过再提交。
5. **敏感操作前先问**：删文件、合并 main、强制推送（`--force`）、数据库 DROP 表，必须先征得用户明确同意。
6. **提交消息按 `type: description` 中文描述**。Commit 前先 `git diff --staged` 确认没有把 `.env` / `data.db` / `.qoder/` 加进去。
7. **遇到图表/模板变更不生效**，优先提示用户查端口占用（坑 3），不要先怀疑代码。
8. **项目结构/分支策略/安全约定有重大变更时**，记得更新本 CODEBUDDY.md，并 commit 到 develop。
9. **不要删除 `.codebuddy/` 目录**，这是 CodeBuddy 工作数据目录。
10. **不要创建多余文件**，优先用 `replace_in_file` 修改现有文件。
11. **不要用 print 替代 logging**。
12. **不要移除采集的 5 页上限**。
13. **不要在启动时预计算模型**（懒加载设计）。
14. **git push 后自动更新 README.md**（用户明确要求）。
15. **未经用户验证确认就 git push**（必须等验证通过后再推送）。
16. **意义不大的微小改动不单独提交**（如仅删一个临时文件、改一行 .gitignore），攒着和后续实质性改动一起提交。
17. **回退操作默认只回退到本次任务执行前的状态**，不进行 `git checkout` / `git restore`。当用户说"回退""撤销""恢复原样"时，指的是撤销当前对话中已做的改动，不是回到 git 提交版本。只有当用户明确说"回退到 git""回退到上次提交"时才使用 git 回退。

---

## 10. 最近变更记录（Changelog 摘要）

- 2026-07-05 · `refactor: advice 页面移除技能关键词提取 tab（与图表页词云功能重叠）`
- 2026-07-05 · `feat: 职位分类与技能提取全面数据驱动化，支持任意行业岗位采集后自动适配`
- 2026-07-05 · `chore: ARCHITECTURE.md 并入 CODEBUDDY.md，统一为单一真相来源`
- 2026-07-04 · `test: 新增 test_agent_tools.py(11) + test_cross.py(11) + RF/cache 测试(7),覆盖 compare_jobs/extract_skills/交叉分析/RF训练/缓存;全量 126 passed`
- 2026-07-04 · `feat: 薪资预测新增 RandomForest 对比模型(三模型对比)、Agent 新增 compare_jobs/extract_skills 工具、图表页新增薪资vs经验/学历交叉分析图`
- 2026-07-03 · `feat: 新增文档(ARCHITECTURE.md 项目架构与规范)，统一 AI 开发上下文`
- 2026-07-03 · `chore: Git 分支体系落地（main 保护 + develop 开发双分支），远程 main 设置 PR 合并规则`
- 2026-07-01 · `security: CSRF + Flask-Limiter + COLLECT_TOKEN + Agent 参数白名单 + 分页输入校验（97 个测试全过）`
- 2026-07-01 · `perf: sklearn/jieba 懒加载 + 三段进度打印，Flask 秒启`
- 2026-07-01 · `fix: Debug 开关改由 .debug 文件判定，根治 FLASK_DEBUG 残留导致 reloader 伪装退出`
- 2026-07-01 · `docs: README 对齐项目现状 + docker-compose 开发热更新挂载 + .qoder gitignore`

---

## 11. CodeBuddy 专属上下文

### 11.1 用户环境

- **OS**: Windows 10/11，PowerShell
- **IDE**: CodeBuddy（原名 Trae）
- **工作目录**: `f:\Desktop\project1`
- **启动命令**: `python app.py`（venv）
- **端口**: `http://127.0.0.1:5000`

### 11.2 用户偏好

- 演示场景为主，数据量几十条即可，但项目能力可达 1000+
- 采集上限保持 5 页/城市，不要扩大
- Debug 默认关闭（.debug 文件不创建）
- **git push 后自动更新 README.md**（用户的明确要求）
- 回答要简洁直接，中文

### 11.3 已确认的设计决策

- **Debug 模式**：默认 off（`.debug` 文件不存在时），**off 是正常状态，不是错误**
- **图表**：`/chart` 每次请求实时跑 4 个统计函数（无缓存），设计如此
- **ML 加载**：`/ml` 首次访问触发 KMeans + 薪资模型训练（懒加载），用户接受演示延迟
- **数据量**：演示时几十条足够，项目能力轻松 1000+

### 11.4 关键代码位置

```
app.py:482-483    → Debug 开关逻辑（.debug 文件）
app.py:190-203    → 模型懒加载（_get_clustering）
app.py:254-264    → /chart 路由（每次实时计算）
app.py:281-294    → /ml 路由（首次触发训练）
app.py:377-381    → 采集页数上限（max=5）
app.py:500        → app.run() 最终配置
app.py:515-531    → 采集后模型重训 + cache.invalidate()
config.py:43      → DEEPSEEK_API_KEY
config.py:47      → COLLECT_TOKEN
modeling/cache.py → 模型缓存单例（get/update/invalidate）
analysis/jobtitle.py → classify() 跨行业 RULES（5层优先级:具体角色→级别→方向→职能→兜底）
```

---

> 最后更新: 2026-07-05
