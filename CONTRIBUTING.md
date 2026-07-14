# 贡献指南

感谢你愿意为 job-crawler 做出贡献。本文档说明如何参与开发、代码规范以及如何提交改动。

## 开发环境搭建

```bash
git clone https://github.com/cloudy-one1/job-crawler.git
cd job-crawler

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # 按需填写 LLM 密钥，不填也能跑除 AI 外的全部功能
python app.py                      # http://127.0.0.1:5000
```

需要运行采集功能时，额外安装一次浏览器内核：

```bash
playwright install chromium
```

## 分支与提交

- `main` —— 稳定分支，受保护，只能通过 Pull Request 合入
- `develop` —— 日常开发分支，PR 默认合入这里

提交信息遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/v1.0.0/)：

```
feat: 新增学历溢价分析
fix: 修复分页参数越界导致 500
docs: 补充配置文件说明
refactor: 抽取数据库连接公共逻辑
test: 补充薪资解析器边界用例
chore: 更新依赖版本
```

## 代码规范

- 遵循 PEP 8，缩进 4 空格；仓库根目录的 `.editorconfig` 已配置好，主流编辑器会自动生效
- **分层依赖不可倒置**：`data/ → analysis/ → modeling/ → agent/ → app.py`，下层模块不得引用上层
- 新增配置常量统一放在 `config.py`，通过环境变量读取，**禁止硬编码密钥**
- 新增 POST 路由必须加 CSRF 保护（Flask-WTF），模板中使用 `{{ form.hidden_tag() }}`
- 重型库（`sklearn` / `jieba` / `pandas`）相关模块请保持懒加载，避免拖慢启动
- 模块级缓存变量集中声明在 `app.py` 顶部的「模块级状态」区块，不要散落定义

## 测试

```bash
pytest                       # 全量
pytest tests/test_cross.py   # 单个文件
```

提交 PR 前请确保全量测试通过。新增功能请附带对应用例，测试应使用临时数据库或 mock，**不得依赖本地 `data.db`**。

## Pull Request 流程

1. Fork 本仓库并基于 `develop` 创建分支，例如 `feature/skill-trend`
2. 完成改动、补充测试、确保 `pytest` 全绿
3. 提交 PR 到 `develop`，按模板填写改动说明与自测情况
4. 等待 CI 通过和 Review，维护者合并后分支可删除

## 报告问题

- Bug → [Bug 报告模板](.github/ISSUE_TEMPLATE/bug_report.yml)
- 新功能建议 → [功能请求模板](.github/ISSUE_TEMPLATE/feature_request.yml)
- 安全问题请**不要**开公开 issue，参见 [SECURITY.md](SECURITY.md)

## 行为准则

参与本项目即表示同意遵守 [行为准则](CODE_OF_CONDUCT.md)。
