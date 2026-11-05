# 算法数据接口契约（技术版）

> 本文件是飞书《算法数据接口清单》与 5 号《数据存储设计说明书》的**技术速查版**，供成员B 建库 / 写 ETL 时对照。
> 叙述性说明与变更讨论以**飞书文档为准**；两边若不一致，请在飞书确认后同步修改本文件。

## 1. 数据链路

```
data/raw 原始数据包（组长提供）
  → 成员B: HDFS 落地 → Spark SQL 清洗 → ODS / DWD / DWS 分层
  → ADS 层 ads_graph_node / ads_graph_edge（算法输入）
  → 组长: algorithm 引擎读取并计算
  → 结果文件 data/processed/ 与 ADS 结果表
  → 成员C: Superset / Web 看板
```

本地模式与生产模式只在「接入层」不同：本地用 `load_airports()/load_routes()` 解析文件，
生产模式用 `load_from_hive()` 查 ADS 表，之后的构图、指标、导出逻辑完全一致。

## 2. 算法直接读取的两张 ADS 表

### `ads_graph_node`（机场维表 / 图节点）

| 字段 | 类型 | 约束 | 算法用途 |
|---|---|---|---|
| `airport_code` | STRING | PK，IATA 三字码 | 节点唯一 ID |
| `airport_name` | STRING | | 展示 |
| `province` | STRING | | 展示 / 区域筛选兼容字段 |
| `lat` / `lng` | DOUBLE | | 可视化（可选） |
| `annual_throughput` | BIGINT | >=0 | 真实年旅客吞吐量，利用率分子 |
| `designed_capacity` | BIGINT | >0 | 真实设计容量，利用率分母 |
| `capacity_ratio` | DOUBLE | >=0 | 容量利用率，触发饱和预警 |
| `node_weight` | DOUBLE | 默认 1.0 | 节点权重（默认取吞吐） |

### `ads_graph_edge`（航段 / 图边表）

| 字段 | 类型 | 约束 | 算法用途 |
|---|---|---|---|
| `from_airport_code` | STRING | PK 组合 | 起点（节点 ID） |
| `to_airport_code` | STRING | PK 组合 | 终点（节点 ID） |
| `edge_weight` | DOUBLE | >0 | 边权，用于中心性 / 边瓶颈 |
| `flight_count` | INT | >=0 | 辅助展示 |
| `route_throughput` | BIGINT | >=0 | 边权备选 |

## 3. 关键约定（建库时务必遵守）

1. **节点 ID 统一用 `airport_code`（IATA 三字码）**。本地样本用 OpenFlights 数字 ID 只是为了对齐 `.dat`，切换 Hive 后所有下游按字符串代码处理。
2. **必须保留 `country` 字段**（值域 `China` / `Hong Kong` / `Macau` / `Taiwan`，含港澳台）。区域子图筛选依赖它；若 ADS 表只提供中文 `province`/`city`，算法虽做了中文别名兼容，但纯省份名无法判定国别，**中国子图可能为空**。
3. **吞吐与容量是两张独立数据，不能互相代替**。容量饱和预警用的是 `真实吞吐 ÷ 真实设计容量`；"高吞吐量预警"只是辅助参考列，不作为容量饱和判定。
4. **缺容量数据的机场**：`designed_capacity` 留空，算法自动把利用率计 0、不计入预警，不要填统一占位值。
5. **边权 `edge_weight` 需在构图时覆盖频次权重**：Hive 模式的边权来自 ADS，不是"重复航段计数"。接入 `load_from_hive()` 时给 `graph_builder.build_graph()` 增加可选 `edge_weights` 参数即可，上层指标代码不用改。

## 4. 已确认的算法参数（不再改动）

| 参数 | 值 | 含义 |
|---|---|---|
| α (ALPHA) | 0.6 | 耦合权重中利用率项占比 |
| β (BETA) | 0.4 | 耦合权重中中心性项占比 |
| τ1 (TAU1) | 0.75 | 一级预警阈值（偏繁忙） |
| τ2 (TAU2) | 0.90 | 二级预警阈值（接近饱和） |
| k | 800 | 介数中心性抽样数（仅全局大图；小图自动精确） |
| VULN_TOP_K | 3 / 5 / 10 / 20 | 脆弱性仿真累计移除的 Top-K 节点数 |

## 5. 生产模式接入清单（成员B 就绪后）

- [ ] 提供 HiveServer2 地址 / 端口 / 账号 / 数据库，填入 `algorithm/config.py` 的 `HIVE_CONFIG`
- [ ] 建好 `ads_graph_node` / `ads_graph_edge`，字段与上表一致，并启动 HiveServer2
- [ ] 安装 `pyhive`、`thrift`，实现 `loader.load_from_hive()`（4 步约定见其函数文档）
- [ ] 用中国子图节点数（本地基线 **270**）和容量预警数（本地基线 全局 **8** / 中国 **2**）作为联调校验值

> 本地基线（2026-11-05 实跑）：全局 7698 节点 / 36906 边；中国子图 270 节点 / 3108 边；
> 真实吞吐量 94 条（对照上 91 个节点）、真实设计容量 20 条（对照上 19 个节点）。
