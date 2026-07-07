# 招聘数据分析与可视化系统

一个基于 Python 的招聘市场数据分析全栈项目，提供从数据采集、存储、分析到可视化展示的完整流程，并集成了基于大语言模型的智能问答功能。

## 核心功能

| 模块 | 功能 | 技术 |
|------|------|------|
| 数据采集 | 51job 实时职位抓取（多城市×5 页上限） | Playwright (Chrome 无头) + stealth 对抗 WAF |
| 数据清洗 | 薪资解析、jobTags 关键字提取 | 正则 + 规则引擎 |
| 描述性统计 | 薪资/学历/经验/城市分布 + 交叉分析 | Pandas + SQLite |
| 职位聚类 | 自动发现职位方向，支持点击簇卡片查看明细 | Jieba 分词 + TF-IDF + KMeans + 轮廓系数 |
| 多维薪资分析 | 技能供需热力图、经验-薪资成长曲线、学历溢价分析、岗位相似度网络 | NumPy + SQLite + 余弦相似度 |
| 技能词云 | 仅从 51job 官方 jobTags 提取，echarts-wordcloud 圆形布局渲染 | 同义词归一化 + 停用词白名单过滤 |
| AI 图表解读 | 6 个图表区段点击即 AI 分析（服务端 5 分钟缓存） | AJAX + call_llm_with_fallback (DeepSeek → 千问) |
| AI 建模解读 | 聚类/热力图/相似度/薪资曲线/学历溢价 5 维度 AI 解读 | 同上 + 各模块数据拼装 |
| AI Agent 问答 | 预加载 DB 概览 → 单次 LLM → 双段式输出（数据结论+普适建议） | DeepSeek/千问双模型 fallback |
| 城市对比 | 两城并排对比 + 技能差异 + AI 解读 | agent_tools.compare_jobs + LLM |
| 岗位匹配推荐 | 六维度透明评分（技能35%+城市15%+学历15%+经验15%+薪资10%+真实性10%） | 规则驱动 + Critic 校验 + Gap 分析 |
| 简历审查优化 | 技能提取→岗位Gap→双Agent深度分析（Critic诊断+Optimizer重写） | resume_parser (PDF/DOCX) + LLM 双 Agent |
| 岗位收藏 | 感兴趣岗位清单，支持跨页面勾选、全选/清空、匹配时限制范围 | session 存储，零数据库迁移 |
| 预热机制 | 首页静默 AJAX 预计算全部图表+模型，页面秒开 | /api/warmup (CSRF exempt) |
| Docker 部署 | 一键容器化运行（爬虫宿主机、Web容器内） | Docker + docker-compose + volume 热更新 |

> **容错设计**：空数据库首次启动不会崩溃，所有页面友好提示"请先采集数据"，无需预先准备任何数据。
>
> **安全加固**（对抗式审查后修复）：
> - 非法页码输入自动回退，防止 500 崩溃
> - 数据采集采用原子写入，采集中断不会丢失旧数据
> - 数据库异常不再静默吞掉，打印警告日志便于排查
> - URL 参数自动转义，防特殊字符截断
> - Agent API 调用带指数退避重试，网络抖动不直接失败
> - 前端异常信息脱敏，不泄露内部路径和堆栈
> - **全站点 CSRF 防护**（Flask-WTF）：所有 POST 路由强制校验 token（`/api/warmup` 除外），防跨站伪造提交
> - **secret_key 安全注入**：从 `FLASK_SECRET` 环境变量读取，未设时使用 `os.urandom(32)` 随机值
> - **debug/host 默认关闭**：无 `.debug` 文件时 Debug=off + reloader=off，`FLASK_HOST` 默认 `127.0.0.1`
> - **采集口令保护**：`.env` 配置 `COLLECT_TOKEN` 后，采集需输入口令，防误操作清空数据
> - **速率限制**（Flask-Limiter）：全局 50/小时 + 采集接口 5/小时，防滥用
> - **SQLite WAL 模式**：启动时自动启用，并发读不再被写操作锁库
> - **Agent 工具调用**：工具函数参数由代码层预定义并直接调用，不经 LLM 动态传参，避免非法参数
> - **分页链接 `url_for()`**：自动 URL 编码，杜绝手动拼接的安全隐患
>
> **工程质量**（代码健壮性提升）：
> - **数据库连接管理**：Flask `g` 对象复用连接 + `teardown_appcontext` 自动关闭，避免连接泄漏
> - **模型持久化**：joblib 缓存聚类模型到磁盘 (`cache/`)，服务器重启免重训
> - **日志系统**：`logging` + `RotatingFileHandler` 替代 `print`，分级输出到 `logs/app.log`（5MB 旋转 × 3 备份）
> - **启动性能优化**：sklearn / jieba / pandas 懒加载，Flask 秒启不再误判卡死
> - **预热机制**：首页 `/api/warmup` 静默预计算全部图表+模型+建模模块，后续页面秒开
> - **Debug 机制**：根目录 `.debug` 文件开关，根治环境变量残留导致 reloader 伪装退出

## 项目结构

```
project1-enhanced/
├── app.py                    # Flask 入口 (Web 服务 + 路由)
├── config.py                 # 配置 (数据库路径、API Key 从 .env 读取)
│
├── data/                     # 数据层：采集 + 清洗
│   ├── python_job_scraper.py    — 51job 实时采集 (Playwright + stealth)
│   └── salary_parser.py         — 薪资字符串解析 (1.5-2万/月 → 千元数值)
│
├── analysis/                 # 分析层：统计 + 可视化数据生成
│   ├── xinzi.py                 — 薪资分段统计 (8 档/千元)
│   ├── xueli.py                 — 学历分布统计
│   ├── jinyan.py                — 经验分布统计
│   ├── region.py                — 城市分布统计 (含 extract_city 共享工具)
│   ├── cross.py                 — 交叉分析 (薪资 vs 经验 / 薪资 vs 学历)
│   ├── jobtitle.py              — 职位标题规则分类 (40+行业 100+规则,5层优先级)
│   └── wordcloud_gen.py         — 技能词云 (51job jobTags + 同义词归一化 + 圆形布局)
│
├── modeling/                 # 模型层：机器学习 + 多维分析
│   ├── job_clustering.py        — KMeans 无监督聚类 (TF-IDF 技能向量 + 自动 k 选择 + 轮廓系数)
│   ├── salary_predict.py        — 薪资统计查询 (DB 驱动: 中位数/均值/分位数,非模型预测)
│   ├── skill_heatmap.py         — 技能供需热力图 (城市×技能 薪资矩阵,keywords fallback 正则)
│   ├── job_similarity.py        — 岗位相似度网络 (余弦相似度,转型路径建议)
│   ├── salary_curve.py          — 薪资成长曲线 (经验-薪资趋势,按方向/city分组)
│   └── edu_premium.py           — 学历溢价分析 (硕士vs本科vs大专,按城市+方向分层)
│
├── agent/                    # Agent 层：大模型对话
│   ├── agent_core.py            — LLM 调用封装 (DeepSeek/千问双模型 fallback + 指数退避重试)
│   ├── agent_tools.py           — 10 个工具函数: query_jobs / skill_demand_analysis / category_overview /
│   │                               city_overview / edu_overview / exper_overview / predict_salary /
│   │                               compare_jobs / match_jobs(六维度) / review_resume(双Agent)
│   └── resume_parser.py         — 简历文件解析 (PDF→PyPDF2 / DOCX→python-docx → 纯文本)
│
├── templates/                # HTML 模板 (10 个页面, ECharts 可视化)
│   ├── base.html                 — 公共基础模板 (导航栏 + 收藏计数 Badge)
│   ├── input.html                — 首页: 关键词输入 + 省市联动选择器 + 采集入口
│   ├── data.html                 — 数据总览: 分页列表 + 城市/JD 精确搜索 + 岗位悬停放大
│   ├── job_detail.html           — 岗位详情: 完整信息 + 51job 原文跳转 + 收藏按钮
│   ├── h.html                    — 图表页: 6 区段(薪资/学历/经验/城市/词云/交叉) + AI 解读
│   ├── ml.html                   — 建模页: 聚类方向卡片 + 热力图 + 相似度 + 薪资曲线 + 学历溢价
│   ├── cluster_jobs.html         — 方向岗位明细列表 (点击 ml 方向卡片进入)
│   ├── advice.html               — Agent 页: 4-tab(Agent问答/城市对比/岗位匹配/简历审查)
│   ├── interested.html           — 收藏清单: 全选/清空/批量定位/对比清单
│   └── collect.html              — 采集管理: 关键词+城市+页数+排序+采集口令+结果展示
│
├── tests/                    # 测试 (226 个用例, 全部通过, 覆盖率 > 90%)
│   ├── test_app_routes.py       — 路由与安全回归测试 (CSRF/限流/分页/输入校验)
│   ├── test_advice_route.py     — advice 4-tab 回归测试 (Agent/Compare/Match/Review)
│   ├── test_agent_loop.py       — Agent 核心逻辑集成测试
│   ├── test_agent_tools.py      — Agent 工具函数测试 (query_jobs/match_jobs/review_resume等)
│   ├── test_cross.py            — 交叉分析函数测试 (salary_vs_exper/salary_vs_edu)
│   ├── test_python_job_scraper.py — 采集参数构建单元测试
│   ├── test_salary_parser.py    — 薪资解析全覆盖测试
│   ├── test_analysis_functions.py — classify/extract_city/tokenize 分析函数测试
│   ├── test_job_detail.py       — 岗位详情页回归测试
│   ├── test_model_logic.py      — 聚类/预测/缓存模型核心逻辑测试
│   └── test_modeling_features.py — 建模模块测试 (学历溢价/薪资曲线/相似度/热力图)
│
├── Dockerfile                # Docker 镜像构建
├── docker-compose.yml        # Docker 一键部署
├── .dockerignore             # Docker 忽略文件
│
├── cache/                    # 模型持久化 (joblib 二进制,切勿手动编辑)
├── logs/                     # 运行时日志 (gitignore, 5MB 旋转 × 3 备份)
│
├── .env.example              # 环境变量示例 (复制为 .env 填入 Key)
├── requirements.txt          # 依赖清单
└── README.md                 # 本文件
```

## 分层依赖关系

```
templates + app.py    ← 展示层
        ↓
agent/                ← Agent 层 (复用分析层+建模层)
        ↓
modeling/             ← 建模层 (依赖分析层的 classify / extract_city)
        ↓
analysis/             ← 描述性统计层 (依赖 config + data.db)
        ↓
data/                 ← 数据层 (采集、解析、清洗)
        ↓
config.py + data.db   ← 基础设施
```

**核心原则**：下层模块不依赖上层。`agent/agent_tools.py` 的 `city_overview` 复用 `analysis/region.extract_city()`；`modeling/salary_predict.py` 复用 `analysis/jobtitle.classify()`。

## 快速开始

### 方式一：本地直接运行（推荐用于开发/演示）

```bash
# 1. 安装依赖
pip install -r requirements.txt
playwright install chromium

# 2. 配置环境变量（.env，仅 Agent / 加固配置需要）
# 复制 .env.example 为 .env，按需填入:
#   DEEPSEEK_API_KEY=你的Key         (主用 AI 模型, Agent 问答 + 图表解读)
#   QWEN_API_KEY=你的千问Key           (备选 fallback, DeepSeek 不可用时自动切换)
#   FLASK_SECRET=64字符随机字符串    (用于 session 和 CSRF token 签名持久化；不填每次启动随机)
#   COLLECT_TOKEN=采集口令          (设置后采集接口要求校验口令，防误操作清空数据；不填不启用)
#   FLASK_HOST=127.0.0.1 / 0.0.0.0  (默认 127.0.0.1；0.0.0.0 才对外监听局域网)
#
#    ※ Debug 开关不再使用环境变量，改为文件开关：
#    ※ 想要启用 debug + reloader（模板热更新）时，在项目根目录 touch 一个空的 .debug 文件即可
#    ※ 日常开发建议保持关闭，否则 reloader 会 fork 子进程导致 print 丢失、端口残留、假退出
#    ※ .debug 文件已被 .gitignore 忽略

# 3. 启动 Web 服务
python app.py
# 终端会自动打印 本地访问(http://127.0.0.1:5000) + 同局域网访问地址

# 4. 命令行独立运行各模块验证
python -c "from analysis.xinzi import xinzi; print(xinzi())"
python -c "from analysis.jobtitle import jobtitlefun; print(jobtitlefun())"
python -c "from analysis.wordcloud_gen import generate_wordcloud_data; print(generate_wordcloud_data(10))"
python -c "from modeling.job_clustering import run_clustering; print(run_clustering())"
python -c "from modeling.skill_heatmap import compute_skill_heatmap; print(compute_skill_heatmap())"
python -c "from modeling.salary_curve import compute_salary_curve; print(compute_salary_curve())"
python -c "from modeling.edu_premium import compute_edu_premium; print(compute_edu_premium())"
python -c "from agent.agent_tools import match_jobs; print(match_jobs('Python,Django','北京','本科','1-3年'))"
python -c "from agent.resume_parser import extract_text; print(extract_text(open('resume.pdf','rb').read(),'resume.pdf'))"
python -m pytest tests/ -v   # 运行全部测试 (226 个用例, 全部通过)
```

### 方式二：Docker 部署（推荐用于服务器/长期运行）

> **架构分工**：数据采集（Playwright + Chromium）依赖真实浏览器指纹对抗 WAF，因此在宿主机本地执行后写入 `data.db`；Docker 容器仅负责 Web 展示 + 模型推理 + Agent，通过 volume 挂载共享同一个 SQLite 数据库。镜像体积约 300MB（不含 Chromium）。

```bash
# 1. 先在本地采集一次数据 (Playwright 需要真实浏览器指纹)
python -c "from data.python_job_scraper import scrape_jobs; scrape_jobs()"

# 2. 启动 Docker 容器 (纯 Web 服务，不含爬虫)
# 方式一: docker-compose (推荐，最简单)
# 注：docker-compose.yml 已挂载 templates/、app.py、config.py 到容器 → 开发期改源码不用重建镜像
# 仅 data.db 持久化数据，模板改动容器立即生效
docker-compose up -d
# 访问 http://localhost:5000

# 方式二: 手动构建与运行
docker build -t job-analysis .
docker run -d -p 5000:5000 \
  -v $(pwd)/data.db:/app/data.db \
  -v $(pwd)/templates:/app/templates:ro \
  -v $(pwd)/app.py:/app/app.py:ro \
  -v $(pwd)/config.py:/app/config.py:ro \
  --env-file .env \
  job-analysis

# 后续更新数据：宿主机重新采集，无需重启容器 (共享 data.db)
```

#### 镜像源配置（国内网络环境）

若 Docker Hub 连接超时，在 Docker Desktop → Settings → Docker Engine 中添加镜像源：

```json
"registry-mirrors": [
  "https://docker.1ms.run",
  "https://docker.xuanyuan.me"
]
```

#### 虚拟机/服务器部署（需要 Python 3.10+）

```bash
git clone <你的仓库地址>
cd project1-enhanced
pip install -r requirements.txt
playwright install chromium      # 仅在需要采集的机器上安装
python app.py                      # 访问 http://<服务器IP>:5000
```

## Web 页面说明

| 路由 | 方法 | 功能 | 模板文件 |
|------|------|------|---------|
| `/` | GET | 首页（关键词 + 城市输入 + 省-市联动） | `input.html` |
| `/api/warmup` | GET/POST | 静默预热：预计算全部图表+聚类+建模模块 | (JSON) |
| `/list` | GET | 职位列表（分页 12/页 + 精确匹配筛选） | `data.html` |
| `/job/<id>` | GET | 职位详情页（含 51job 原文链接跳转） | `job_detail.html` |
| `/chart[/<section>]` | GET | 图表分析页（6 区段：城市/薪资/学历/经验/词云/交叉） | `h.html` |
| `/chart/analyze` | POST | AI 图表解读（6 区段，服务端 5 分钟缓存） | (JSON) |
| `/ml` | GET | 聚类建模页（方向卡片 + 热力图 + 相似度 + 薪资曲线 + 学历溢价） | `ml.html` |
| `/ml/analyze` | POST | AI 建模解读（5 维度，服务端 2 分钟缓存） | (JSON) |
| `/ml/cluster/<id>` | GET | 方向岗位明细列表（点击 ml 方向卡片进入） | `cluster_jobs.html` |
| `/advice` | GET/POST | AI Agent 问答 + 城市对比 + 岗位匹配 + 简历审查（4-tab） | `advice.html` |
| `/advice/compare/analyze` | POST | 城市对比 AI 解读（5 分钟缓存） | (JSON) |
| `/interested` | GET | 感兴趣岗位收藏清单（支持全选/清空/对比） | `interested.html` |
| `/toggle_interest` | POST | AJAX 切换岗位收藏状态（需 CSRF token） | (JSON) |
| `/collect` | GET/POST | 数据采集管理（5 次/小时限流 + 可选口令保护） | `collect.html` |

> 共 14 个对外路由 + 1 个 CSRF 豁免的内部接口（`/advice/active-tab`，前端 tab 状态同步用），合计 15 个路由定义。JSON 接口由前端 AJAX 调用，不直接渲染页面。所有 POST 路由均受 CSRF 保护。`/collect` 单独限流 5 次/小时。

<!-- 变更记录见 git log，或 CODEBUDDY.md 第 10 节 -->
