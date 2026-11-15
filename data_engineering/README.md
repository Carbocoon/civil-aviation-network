# 数据工程（2313040123 段亦弢）

本目录负责民航航线网络的数据入仓、ETL 与图数据库导入，数据链路：

```text
项目根 data/raw（真实原始数据包）
  -> ODS（贴源层）
  -> DWD（清洗明细层）
  -> DWS（机场/航段汇总层）
  -> ADS（算法图节点/边 + 算法结果表）
  -> 算法引擎（本地模式 / HiveServer2 模式） → data/processed → Streamlit 看板
```

## 目录与文件

```text
data_engineering/
├── hive_ddl/00_create_tables.sql   # ODS/DWD/DWS/ADS 共 10 张表
├── spark_etl/aviation_etl.py       # Spark ETL 主作业
├── neo4j_import/import_graph.cypher# Neo4j 幂等导入
└── ETL执行记录.md                   # 5 号《数据存储设计说明书》要求的执行记录附件
```

表统一使用 ORC + Snappy，按 `dt` 分区；图节点、图边和航段统计表按机场代码分 8 桶。
`ads_graph_node` 保留 `country`（含 China / Hong Kong / Macau / Taiwan），节点 ID 使用
IATA 三字码，缺设计容量的机场保持 NULL —— 这三条是《算法数据接口清单》的硬要求。

## 原始数据位置（重要）

四个 raw 文件**随仓库提交**，位于仓库内 `data/raw/`（项目根 `data/raw/` 另有一份
内容一致的交付副本）。早期 `.gitignore` 曾排除 `*.dat` 与 `data/processed/`，现已取消，
clone 后可直接运行 ETL、算法引擎与测试，无需再单独索取数据包。

```text
airports.dat / routes.dat                        OpenFlights 结构数据
airport_throughput_2023.csv                      94 个机场真实年旅客吞吐量
airport_capacity_2023.csv                        20 个机场真实设计容量（带来源）
```

作业会按以下顺序自动查找含四个文件的目录，**无需手写绝对路径**：`--input-root` →
环境变量 `CIVIL_AVIATION_PROJECT_ROOT` → 从脚本位置逐级向上查找。四个文件缺任意一个
都会报出已检查的路径清单，不会静默读空。

## 客流字段口径（评审请以此为准）

公开的 OpenFlights 数据只有「机场年旅客吞吐量」，**没有逐航段实际客流**。因此
`dwd_flight_segment.segment_throughput` 及其派生字段是**按航段频次分摊的估算值**，公式：

```text
航段估算客流 = 始发机场真实年旅客吞吐量 × (该航段航班数 / 该机场出港总航班数)
total_seat   = 航班数 × 180（单班次平均座位假设，见 aviation_etl.py 常量）
avg_load_factor = min(航段估算客流 / total_seat, 1.0)
capacity_utilization = max(起点、终点机场的真实容量利用率)
```

- 估算值用于支撑「容量流量下钻 / 吞吐量排序」的**相对比较**，不代表实际售票数据；
- `edge_weight` 优先取估算客流（>0 时），否则回退航班数；
- **容量饱和预警只用真实吞吐量 ÷ 真实设计容量**，完全不受估算影响；
- 缺设计容量的机场 `designed_capacity` 保持 NULL，容量利用率按 0 处理，不填占位值。

## 运行 ETL

在集群客户端（仓库根目录）执行，首次先建表：

```bash
spark-sql --hivevar database=civil_aviation \
  -f data_engineering/hive_ddl/00_create_tables.sql
```

从本地 raw 数据包构建（默认，自动定位项目根 data/raw）：

```bash
spark-submit data_engineering/spark_etl/aviation_etl.py \
  --source local --database civil_aviation --dt 2026-11-13
```

也可显式指定数据目录，或直接读集群已有 ODS 分区：

```bash
spark-submit data_engineering/spark_etl/aviation_etl.py \
  --source local --input-root /path/to/项目根/data/raw --dt 2026-11-13

spark-submit data_engineering/spark_etl/aviation_etl.py \
  --source ods --database civil_aviation --dt 2026-11-13
```

作业已开启 `spark.sql.sources.partitionOverwriteMode=dynamic`，只覆盖本次 `dt` 分区，
不误删历史分区；所有 `insertInto` 的 select 列顺序与 DDL 完全一致（按位置匹配）。
运行结束会打印 `ads_graph_node` / `ads_graph_edge` 本分区行数，便于与算法基线核对。

## 与算法侧的规模差异（必须说明，不是 bug）

| 口径 | 节点 | 边 |
|---|---|---|
| ETL（ADS 层，IATA 三字码） | 6072 | 37041 |
| 算法本地基线（OpenFlights 数字 ID） | 7698 | 36906 |

原因有三，均与清洗规则有关：

1. **节点键不同**：ETL 用 IATA 三字码并过滤非 3 字码/空码；算法本地用 OpenFlights
   数字 ID，包含少量无 IATA 码但仍可构图的机场；
2. **边聚合口径不同**：ETL 按 `(from,to)` 聚合成一条航段（多条航司记录合并为
   `flight_count`），算法本地也聚合但保留直飞判定与自环剔除规则略有差异；
3. **ETL 额外要求两端机场都在有效机场表内**，孤立航段不进入 ADS。

因此两套数值不要求相等，**量级与 Top 枢纽排序应接近**。切换到 Hive 模式后算法直接读
ADS 两张表，规模以 6072/37041 为准，指标逻辑不变。

## 算法侧 Hive 联调

算法侧 `load_from_hive()` 已实现（`algorithm/loader.py`），集群就绪后：

```bash
set CIVIL_AVIATION_SOURCE=hive
set CIVIL_AVIATION_HIVE_HOST=<HiveServer2 所在节点 IP>
set CIVIL_AVIATION_HIVE_DT=2026-11-13
python -m algorithm.engine
```

算法会把结果再导出为 `data/processed/hive_load/` 下的 5 个 CSV + `load_results.hql`，
在 Hive 节点执行该 HQL 即可回灌 ADS 结果表，形成「Hive 取数 → 算法 → Hive 落库」闭环。
本目录的 Spark ETL 本身不依赖 HiveServer2。

## Neo4j 导入

先将 ADS 最新分区导出为带表头的 CSV，再执行：

```bash
cypher-shell -d neo4j \
  --param 'nodes_file=>"file:///ads_graph_node.csv"' \
  --param 'edges_file=>"file:///ads_graph_edge.csv"' \
  -f data_engineering/neo4j_import/import_graph.cypher
```
