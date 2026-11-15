# 算法数据接口契约（技术版）

> 本文件是飞书《算法数据接口清单》与 5 号《数据存储设计说明书》的**技术速查版**，供成员B 建库 / 写 ETL 时对照。
> 叙述性说明与变更讨论以**飞书文档为准**；两边若不一致，请在飞书确认后同步修改本文件。

## 1. 数据链路

```
data/raw 原始数据包（组长提供）
  → 成员B: HDFS 落地 → Spark SQL 清洗 → ODS / DWD / DWS 分层
  → ADS 层 ads_graph_node / ads_graph_edge（算法输入）
  → 组长: algorithm 引擎读取并计算
  → 结果文件 data/processed/ + 5 张 ADS 结果表（load_results.hql 回灌）
  → 成员C: Streamlit 看板（只读结果文件）
```

本地模式与生产模式只在「接入层」不同：本地用 `load_airports()/load_routes()` 解析文件，
生产模式用 `load_from_hive()` 查 ADS 表并带回 `edge_weights`，之后的构图、指标、导出逻辑完全一致。
切换开关为环境变量 `CIVIL_AVIATION_SOURCE=local|hive`。

## 2. 算法直接读取的两张 ADS 表

字段名与 `data_engineering/hive_ddl/00_create_tables.sql` 保持一致；两张表均按 `dt` 分区。

### `ads_graph_node`（机场维表 / 图节点）

| 字段 | 类型 | 约束 | 算法用途 |
|---|---|---|---|
| `airport_code` | STRING | PK，IATA 三字码 | 节点唯一 ID |
| `airport_name` | STRING | | 展示 |
| `city` / `country` / `province` | STRING | | 展示；`country` 用于区域子图筛选 |
| `lat` / `lng` | DOUBLE | | 可视化（可选） |
| `annual_throughput` | BIGINT | >=0 | 真实年旅客吞吐量，利用率分子 |
| `designed_capacity` | BIGINT | >0，可空 | 真实设计容量，利用率分母 |
| `capacity_ratio` | DOUBLE | >=0 | 容量利用率，触发饱和预警 |
| `node_weight` | DOUBLE | 默认 1.0 | 节点权重（默认取吞吐） |

### `ads_graph_edge`（航段 / 图边表）

| 字段 | 类型 | 约束 | 算法用途 |
|---|---|---|---|
| `from_airport_code` | STRING | PK 组合 | 起点（节点 ID） |
| `to_airport_code` | STRING | PK 组合 | 终点（节点 ID） |
| `edge_weight` | DOUBLE | >0 | 边权，用于中心性 / 边瓶颈 |
| `flight_count` | INT | >=0 | 辅助展示 |
| `route_throughput` | BIGINT | >=0 | 航段估算客流 |

> 航段级客流无公开真实值，ETL 按「始发机场真实年吞吐量 × 该航段航班数占比」估算，
> 口径见 `data_engineering/README.md`，不得与机场吞吐量混用。

## 3. 关键约定（建库时务必遵守）

1. **节点 ID 统一用 `airport_code`（IATA 三字码）**。本地样本用 OpenFlights 数字 ID 只是为了对齐 `.dat`，切换 Hive 后所有下游按字符串代码处理。
2. **必须保留 `country` 字段**（值域 `China` / `Hong Kong` / `Macau` / `Taiwan`，含港澳台）。区域子图筛选依赖它；若 ADS 表只提供中文 `province`/`city`，算法虽做了中文别名兼容，但纯省份名无法判定国别，**中国子图可能为空**。
3. **吞吐与容量是两张独立数据，不能互相代替**。容量饱和预警用的是 `真实吞吐 ÷ 真实设计容量`；"高吞吐量预警"只是辅助参考列，不作为容量饱和判定。
4. **缺容量数据的机场**：`designed_capacity` 留空，算法自动把利用率计 0、不计入预警，不要填统一占位值。
5. **边权 `edge_weight` 覆盖频次权重**：`build_graph(..., edge_weights=...)` 已实现，Hive 模式直接用 ADS 的 `edge_weight`，本地模式仍按航段记录计数；非法或缺失权重回退 1.0。

## 4. 已确认的算法参数（不再改动）

| 参数 | 值 | 含义 |
|---|---|---|
| α (ALPHA) | 0.6 | 耦合权重中容量利用率项占比 |
| β (BETA) | 0.4 | 耦合权重中中心性项占比 |
| τ1 (TAU1) | 0.75 | 一级预警阈值（偏繁忙） |
| τ2 (TAU2) | 0.90 | 二级预警阈值（接近饱和） |
| k | 800 | 介数中心性抽样数（仅全局大图；小图自动精确） |
| VULN_TOP_K | 3 / 5 / 10 / 20 | 脆弱性仿真累计移除的 Top-K 节点数 |

## 5. 结果回灌（已实现）

`algorithm/hive_writer.py` 在 `data/processed/hive_load/` 生成 5 份**无表头** CSV 与 `load_results.hql`。
把该目录整体拷到 Hive 节点，在该目录下执行 `hive -f load_results.hql`，即完成
「Hive 取数 → 算法 → Hive 落库」闭环。

> ADS 结果表按设计是 ORC + Snappy，而算法导出的是 CSV；Hive 的 `LOAD DATA LOCAL INPATH`
> 只搬文件、不做格式转换，直接灌进 ORC 表会导致读表失败。脚本因此为每张表建
> TEXTFILE 临时表接住 CSV，再 `INSERT OVERWRITE ... SELECT` 由 Hive 转成 ORC 写入 `dt` 分区，
> 最后删除临时表并 `ANALYZE TABLE` 更新统计信息。

| 结果表 | 文件 | 内容 |
|---|---|---|
| `ads_centrality_result` | `centrality_result.csv` | 度/接近/介数/PageRank |
| `ads_coupling_index` | `coupling_index.csv` | 耦合权重与 α/β |
| `ads_bottleneck_result` | `bottleneck_result.csv` | 航段瓶颈评分与排名 |
| `ads_vulnerability_index` | `vulnerability_index.csv` | 移除 Top-K 后 LCC 收缩 |
| `ads_saturation_warning` | `saturation_warning.csv` | 容量饱和预警分级 |

## 6. 生产模式接入清单

已完成（代码侧，无需再开发）：

- [x] 连接参数改为环境变量读取（`CIVIL_AVIATION_HIVE_HOST/PORT/USER/PASSWORD/AUTH/DB/DT`），源码内不写死地址
- [x] 实现 `loader.load_from_hive()`：读取 ADS 两张图表、字段转换、真实吞吐/容量回传、缺分区报错
- [x] 实现 Hive 边权覆盖与结果回灌 HQL，并有对应单元测试与集成测试

待集群就绪后执行（联调，不是代码缺口）：

- [ ] 成员B 提供 HiveServer2 地址 / 端口 / 账号 / 库名，并启动 HiveServer2
- [ ] 建好 `ads_graph_node` / `ads_graph_edge`（字段与上表一致），写入 `dt` 分区
- [ ] 集群主节点安装 `pyhive`、`thrift`（仅 Hive 模式需要，本地模式不依赖）
- [ ] 先备份项目根 `data/processed/`（Hive 模式会覆盖同名结果文件，答辩演示用的是本地口径）
- [ ] 设 `CIVIL_AVIATION_SOURCE=hive` 跑一次 `python -m algorithm.engine`
- [ ] 把 `data/processed/hive_load/` 整个目录拷到 Hive 节点，在该目录执行 `hive -f load_results.hql`
- [ ] 用中国子图节点数（本地基线 **270**）和容量预警数（全局 **8** / 中国 **2**）作为联调校验值；
      Hive 口径的图规模以成员B ETL 记录 **6072 / 37041** 为准，两套数值不要求相等，
      但量级与 Top 枢纽排序应接近（差异说明见 `data_engineering/README.md`）

> 本地基线（实跑）：全局 7698 节点 / 36906 边；中国子图 270 节点 / 3108 边；
> 真实吞吐量 94 条（对照上 91 个节点）、真实设计容量 20 条（对照上 19 个节点）。
> 成员B 集群 ETL 记录为 6072 节点 / 37041 边，与本地基线口径不同，差异说明见 `data_engineering/README.md`。
