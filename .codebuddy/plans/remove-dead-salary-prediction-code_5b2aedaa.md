---
name: remove-dead-salary-prediction-code
overview: 清理 model/salary_predict.py 中的死代码（ML训练/预测函数），删除 model/cache.py，更新引用和页面标题。
todos:
  - id: strip-dead-ml-code
    content: 清理 modeling/salary_predict.py：删除所有 ML 训练/预测死代码，保留 lookup_salary_range/get_rows/_contains_word 及必要的 import
    status: completed
  - id: delete-cache-py
    content: 删除 modeling/cache.py 整个文件，更新 modeling/__init__.py 文档字符串
    status: completed
  - id: fix-agent-tool-desc
    content: 修正 agent/agent_tools.py 第 901 行 predict_salary 工具描述，不再声称使用线性回归模型
    status: completed
  - id: remove-dead-tests
    content: 裁剪 tests/test_model_logic.py（移除 TestPredictSalarySafe、TestTrainRF、TestModelCache、_make_synthetic_rows）和 tests/test_analysis_functions.py（移除 TestFuzzyMatch）
    status: completed
    dependencies:
      - strip-dead-ml-code
      - delete-cache-py
  - id: update-ui-and-docs
    content: 更新 templates/ml.html 页面标题 + CODEBUDDY.md 项目描述/技术栈/结构说明 + README.md 功能描述
    status: completed
  - id: verify-tests
    content: 运行测试验证：pytest tests/test_app_routes.py + tests/test_model_logic.py + tests/test_analysis_functions.py 全绿
    status: completed
    dependencies:
      - remove-dead-tests
      - update-ui-and-docs
---

## 用户需求

砍掉薪资预测板块。该板块的 ML 模型训练/预测功能（线性回归、随机森林）已成死代码，实际页面已改用数据库统计查询 `lookup_salary_range`。

## 核心改动

- 清理 `modeling/salary_predict.py` 中的 ML 训练/预测死代码，保留数据库统计查询函数
- 删除 `modeling/cache.py`（仅服务薪资预测模型缓存）
- 更新 `agent/agent_tools.py` 中 `predict_salary` 工具描述（不再声称"使用线性回归模型"）
- 更新 `templates/ml.html` 页面标题和 CODEBUDDY.md/README.md 文档
- 移除测试文件中与薪资预测 ML 模型相关的无效测试用例

## 实施范围

### 文件修改清单

#### 1. `modeling/salary_predict.py` — 删除 ML 死代码，保留统计查询

- **保留**：`get_rows()`、`_contains_word()`、`lookup_salary_range()` 及 `import sqlite3`、`import config`、`from analysis.jobtitle import classify`、`import numpy as np`
- **删除**：所有 sklearn 相关 import（`train_test_split`、`LinearRegression`、`RandomForestRegressor`、`OneHotEncoder`、`ColumnTransformer`、`Pipeline`、`r2_score`、`mean_absolute_error`）
- **删除**：`build_dataset()`、`build_model()`、`_train_one()`、`_train_rf()`、`train_and_evaluate()`、`predict_salary()`、`_fuzzy_match()`、`predict_salary_safe()`
- **删除**：`if __name__ == '__main__'` 中的旧版 ML 模型对比输出

#### 2. `modeling/cache.py` — 删除整个文件

该文件仅服务于 `train_and_evaluate()` 的模型缓存，删除后无任何调用方。

#### 3. `modeling/__init__.py` — 更新文档字符串

删除 `模型缓存: from modeling.cache import get, update` 提及。

#### 4. `agent/agent_tools.py` — 修正工具描述（第 901 行）

当前：`'description': '使用线性回归模型预测月薪(千元)。参数: city ...'`
改为：`'description': '基于数据库真实岗位统计查询月薪参考范围(千元)。参数: city ...'`

#### 5. `templates/ml.html` — 更新页面标题（第 71 行）

当前：`岗位聚类分析与薪资预测`
改为：`岗位聚类分析与薪资洞察`

#### 6. `tests/test_model_logic.py` — 删除 4 个无效测试区块

- 类 `TestPredictSalarySafe`（行 126–196）：测试 `predict_salary_safe` 模糊匹配
- 函数 `_make_synthetic_rows`（行 201–222）：仅被 `TestTrainRF` 使用
- 类 `TestTrainRF`（行 225–312）：测试 `_train_rf` 和 `train_and_evaluate`
- 类 `TestModelCache`（行 317–346）：测试 `modeling.cache`
- 更新模块文档字符串，移除对 `salary_predict.predict_salary_safe()` 的提及
保留 `TestRunClustering*`、`TestClusterSalaryStats`、`TestLookupSalaryRange`、`TestContainsWord`。

#### 7. `tests/test_analysis_functions.py` — 删除 1 个无效测试区块

- 类 `TestFuzzyMatch`（行 216–259）：测试已删除的 `_fuzzy_match`

#### 8. `CODEBUDDY.md` — 更新项目描述

- 第 1 节：一句话描述中删除"薪资预测"
- 第 2 节技术栈：删除线性回归/随机森林薪资预测相关描述
- 第 3 节项目结构：更新 `salary_predict.py` 和 `cache.py` 的说明
- 第 11 节关键代码位置：移除 `/predict` 路由说明

#### 9. `README.md` — 同步更新

移除薪资预测相关功能描述，更新测试用例数量。

## 验证方式

- 修改后跑路由冒烟测试：`pytest tests/test_app_routes.py -q --tb=short`
- 跑裁剪后的模型测试：`pytest tests/test_model_logic.py -q --tb=short`
- 手动验证 `/ml` 页面标题更新、`/salary-lookup` 功能正常