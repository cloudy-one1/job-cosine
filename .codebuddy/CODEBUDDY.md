# CODEBUDDY.md — CodeBuddy AI 工作内存

> 本文件是 CodeBuddy 的专属项目上下文。ARCHITECTURE.md 已包含项目通用信息（架构/规范/坑点）。
> **本文件只记录 CodeBuddy 会话中特有的、ARCHITECTURE.md 中没有的补充信息。**

---

## 0. 共享上下文指引

项目完整信息见 **`ARCHITECTURE.md`**（项目通用），本文件不重复。关键速查：

| 你要什么 | 看哪个 |
|---------|--------|
| 项目概述、技术栈 | ARCHITECTURE.md §1-2 |
| 四层架构、文件分工 | ARCHITECTURE.md §3 |
| 配置改哪里 | ARCHITECTURE.md §4 |
| Git 分支规范、commit 格式 | ARCHITECTURE.md §5 |
| 安全约定 | ARCHITECTURE.md §6 |
| 已踩过的坑 | ARCHITECTURE.md §7 |
| 常用命令 | ARCHITECTURE.md §8 |
| AI 行为硬约束 | ARCHITECTURE.md §9 |

---

## 1. CodeBuddy 专属补充

### 1.1 用户环境

- **OS**: Windows 10/11，PowerShell
- **IDE**: CodeBuddy（原名 Trae）
- **工作目录**: `f:\Desktop\project1`
- **启动命令**: `python app.py`（venv）
- **端口**: `http://127.0.0.1:5000`

### 1.2 用户偏好

- 演示场景为主，数据量几十条即可，但项目能力可达 1000+
- 采集上限保持 5 页/城市，不要扩大
- Debug 默认关闭（.debug 文件不创建）
- **git push 后自动更新 README.md**（这是用户的明确要求，见记忆 ID 94209926）
- 不要创建多余文件，优先用 replace_in_file 修改现有文件
- 回答要简洁直接，中文

### 1.3 CodeBuddy 特有目录

- **`.codebuddy/`** — CodeBuddy 工作数据目录，**永远不要删除**

### 1.4 当前分支状态

- 仓库: `https://github.com/cloudy-one1/job-cosine.git`
- 当前在 `main` 分支（注意：TRAE.md 规定日常开发在 `develop`，但目前 git status 显示在 main）
- main 分支有 7 个本地 commit 未 push
- 有未暂存修改: `docker-compose.yml`

---

## 2. 本会话中确认过的设计决策

### 2.1 Debug 模式
- 默认 off（`.debug` 文件不存在时）
- 开启方式: 创建空 `.debug` 文件
- **debug mode: off 是正常状态，不是错误**

### 2.2 图表和 ML 加载慢
- `/chart` 每次请求实时跑 4 个统计函数（无缓存），这是设计如此
- `/ml` 首次访问触发 KMeans + 薪资模型训练（懒加载）
- 用户接受：演示数据量小，延迟可接受

### 2.3 数据量
- 演示时几十条足够
- 项目能力: 单次 5 页/城市 × 多城市 = 轻松 1000+
- 大规模采集需注意 51job WAF 拦截、延时控制

### 2.4 Git 自动记忆
- **push 后自动检查更新 README.md**（用户明确要求）
- 更新内容：新增功能、修复记录、项目结构变化、安全加固

---

## 3. 关键代码位置速查

```
app.py:482-483    → Debug 开关逻辑（.debug 文件）
app.py:190-203    → 模型懒加载（_get_clustering）
app.py:254-264    → /chart 路由（每次实时计算）
app.py:281-294    → /ml 路由（首次触发训练）
app.py:377-381    → 采集页数上限（max=5）
app.py:500        → app.run() 最终配置
config.py:43      → DEEPSEEK_API_KEY
config.py:47      → COLLECT_TOKEN
modeling/cache.py → 模型缓存单例
```

---

## 4. CodeBuddy 行为准则

- ⚠️ **遇到不熟悉的项目背景，先读 `ARCHITECTURE.md`** — 那是唯一真相来源，本文件只是补充
- ⚠️ 重大变更或踩坑后，如果改动是项目通用的 → 更新 `ARCHITECTURE.md`；如果是 CodeBuddy 特有的 → 更新本文件
- ❌ 删除 `.codebuddy/` 目录
- ❌ 在 main 分支直接改代码（应该切到 develop）
- ❌ 用 print 替代 logging
- ❌ 移除采集的 5 页上限
- ❌ 在启动时预计算模型
- ❌ 忽略 git push 后更新 README 的约定
- ❌ 未经用户验证确认就 git push（**用户明确要求：必须等验证通过后再推送**）

---

> 最后更新: 2026-07-03 · 与 ARCHITECTURE.md v2026-07-03 对齐
