# Superset 看板（可选方案）

分工文档允许「Superset 看板配置导出」或「自研前端页面」二选一。本目录为 Superset
方案的数据源与图表规划；当前主交付为 `../web_frontend/` 的 Streamlit 看板。
若答辩要求使用 Superset，按下面清单在 Superset 中配置后，把导出的 Dashboard
JSON / 数据集配置放入本目录。

## 1. 数据源连接

- **Hive**：在 Superset 新增数据库连接，填写成员B 提供的 HiveServer2 地址、端口（默认 10000）、
  账号、数据库名；对应 ADS 结果表。
- **Neo4j（可选）**：图数据库连接，用于航线网络图查询。
- 本地原型阶段：可先把 `data/processed/` 下 CSV 作为上传数据集接入。

## 2. 数据集与图表清单

| 数据集（结果表/文件） | 图表类型 | 对应需求 |
|---|---|---|
| `{label}_airport_metrics.csv` | 条形图（中心性/耦合排行，可选指标列） | 3 中心性排行 |
| `{label}_airport_metrics.csv` | 散点图（吞吐量 × 耦合，颜色=利用率） | 5 吞吐-耦合对比 |
| `{label}_edge_bottleneck.csv` | 表格 / 条形图（瓶颈航段 Top） | 4 瓶颈识别 |
| `{label}_saturation_warnings.csv` | 表格 + 级别着色（二级红 / 一级橙） | 9 饱和预警 |
| `{label}_throughput_warnings.csv` | 折叠辅助表格（标注非饱和度） | 辅助参考 |
| `{label}_vulnerability.json` | 双轴折线（剩余 LCC + 下降比例） | 6 脆弱性评估 |
| 图节点/边表 | 地图或力导向拓扑图 | 1 拓扑展示 |

## 3. Dashboard 组装与交互

- 顶部筛选器：区域（global / china）、国家/地区、预警级别。
- 图表联动：点选机场 → 下钻展示吞吐、容量、利用率、各中心性（需求7）。
- 订阅入口：页面放置预警订阅说明链接（后端订阅逻辑在 `web_frontend` 演示）。
- 报表导出：使用 Superset 自带的图表/看板导出能力（需求8）。

## 4. 配置导出

- 配置完成后，在 Superset 中导出 Dashboard 与对应数据集，JSON 文件放入本目录；
- 在本目录补一份 `README` 说明连接参数（不含密码）、导入步骤与访问地址。
