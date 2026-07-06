---
name: enlarge-ml-charts
overview: 放大 /ml 机器学习页面的 ECharts 图表尺寸，提升视觉可读性。
todos:
  - id: enlarge-ml-charts
    content: 放大 /ml 页面各 ECharts 图表容器高度并微调间距
    status: completed
  - id: verify-ml-render
    content: 运行路由冒烟测试确认 /ml 页面正常渲染
    status: completed
    dependencies:
      - enlarge-ml-charts
---

## 用户要求

放大 `/ml` 机器学习结果页的 ECharts 图表，使页面更美观、信息更易读。

## 功能内容

- 调大当前所有图表容器高度：
- 技能热力图 `skill_heatmap`
- 岗位相似度网络 `similarity_graph`
- 薪资成长曲线 `salary_curve_chart`
- 学历溢价柱状图 `edu_overall_bar`
- 聚类概览图 `cluster_overview`
- 同步微调区块间距、标题留白，保持视觉平衡。
- 保持现有配色、交互与懒加载逻辑不变。

## 修改范围

仅修改前端模板，无后端变更。

## 实现方式

在 `templates/ml.html` 中：

1. 将各 ECharts 容器 `height` 按约 1.3~1.5 倍放大；
2. 热力图动态高度公式同步调大（行高、顶部/底部留白）；
3. 相似度网络从 `520px` 提升至 `720px` 左右，给力导向图更多呼吸空间；
4. 薪资曲线从 `440px` 提升至 `560px` 左右；
5. 学历溢价柱状图从 `300px` 提升至 `420px` 左右；
6. 聚类概览从当前基准 `560px` 提升至 `700px` 左右；
7. 检查 `window.addEventListener('resize', ...)` 或 ECharts 自适应逻辑是否仍有效。

## 测试

- 仅影响 `/ml` 页面渲染，跑 `tests/test_app_routes.py` 的路由冒烟测试即可。
- 无需新增测试用例。