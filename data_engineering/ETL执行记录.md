# 5 号《数据存储设计说明书》执行记录附件

- 项目名称：民航航线网络结构分析系统
- 编制：成员B 段亦弢；组长张鑫雅核对整理
- 记录日期：2026-11-13
- 依据文档：《5.数据存储设计说明书》、《算法数据接口清单》
- 代码位置：`data_engineering/hive_ddl/00_create_tables.sql`、`data_engineering/spark_etl/aviation_etl.py`

## 一、执行环境

| 项 | 说明 |
|---|---|
| 集群 | 小组各成员本机 3 个 CentOS Hadoop 节点，Hive 已安装 |
| 计算 | Spark SQL（enableHiveSupport），ORC + Snappy |
| 数据分区 | `dt`，执行记录使用 `2026-11-13`（对应本轮交付） |
| 本地复核环境 | Windows + Python 3.11；**未安装 PySpark，集群脚本未在本机复跑** |

> 诚实说明：本文中的 ADS 行数（6072 / 37041）来自成员B 的集群执行记录，组长本机未安装
> PySpark，无法独立复跑该作业；算法侧本地基线（7698 / 36906）由组长在本机实跑，可复现。
> 两套数值的口径差异已在 `data_engineering/README.md` 的「与算法侧的规模差异」一节写明。

## 二、建表执行

按 `hive_ddl/00_create_tables.sql` 建 `civil_aviation` 库及 10 张表：

| 分层 | 表名 | 用途 |
|---|---|---|
| ODS | ods_flight_schedule / ods_airport_info / ods_airport_throughput / ods_airport_capacity | 贴源 |
| DWD | dwd_airport / dwd_flight_segment | 清洗明细 |
| DWS | dws_airport_stat / dws_route_stat | 机场/航段汇总 |
| ADS | ads_graph_node / ads_graph_edge | 算法直接读取的图节点与边 |
| ADS 结果表 | ads_centrality_result / ads_coupling_index / ads_bottleneck_result / ads_vulnerability_index / ads_saturation_warning | 算法结果回灌 |

全部按 `dt` 分区，`dwd_airport` / `dwd_flight_segment` / `dws_route_stat` /
`ads_graph_node` / `ads_graph_edge` 按机场代码分 8 桶。

## 三、ETL 执行步骤

1. `spark-sql --hivevar database=civil_aviation -f hive_ddl/00_create_tables.sql` 建库建表；
2. `spark-submit spark_etl/aviation_etl.py --source local --dt 2026-11-13`
   —— 自动定位项目根 `data/raw` 的四个真实数据文件，先写 ODS 再从 ODS 逐层加工；
3. 作业结束打印本分区 `ads_graph_node` / `ads_graph_edge` 行数；
4. 可选：`--source ods` 直接读已入仓的 ODS 分区重跑，不重复写 ODS。

关键处理：机场代码去空格转大写并过滤非 3 字码；经纬度转 double；按 `(from,to)`
聚合航段并统计 `flight_count`；按「始发机场真实吞吐量 × 航段频次占比」估算航段客流；
缺设计容量保持 NULL；`edge_weight` 优先取估算客流，否则回退航班数。

## 四、字段契约核对（对照《算法数据接口清单》）

| 硬要求 | 落实情况 |
|---|---|
| 必须保留 `country`（含港澳台） | ✅ `ads_graph_node.country` 存在，值来自 OpenFlights 国家字段 |
| 节点 ID 统一 IATA 三字码 | ✅ `airport_code` 即 IATA，算法 Hive 模式按字符串代码构图 |
| 缺容量留空、不填占位值 | ✅ `designed_capacity` 为 NULL，`capacity_ratio` 按 0 处理 |
| 吞吐与容量是两个独立量 | ✅ 分别取自 ODS 两张真实数据表，不互相代替 |
| 边权覆盖频次权重 | ✅ `ads_graph_edge.edge_weight` 由算法构图时传入 `edge_weights` |

## 五、校验结果

| 校验项 | 结果 |
|---|---|
| 算法本地实跑（组长本机，可复现） | 全局 7698 节点 / 36906 边；中国子图 270 / 3108 |
| 算法本地实跑（真实数据接入） | 真实吞吐 94 条、真实容量 20 条 |
| 容量饱和预警 | 全局 8 个、中国子图 2 个（SHA 1.062319 二级、HGH 0.823409 一级） |
| 单元测试 | 23 项全部通过（含 Hive 模式数据转换、边权覆盖、结果回灌脚本） |
| 集群 ETL（成员B 记录） | ads_graph_node 6072 行 / ads_graph_edge 37041 行 |
| Hive 取数链路 | `load_from_hive()` 已实现，用假 HiveServer2 游标完成转换逻辑单测 |
| 结果回灌 | `data/processed/hive_load/load_results.hql` 已生成，含 5 张结果表 LOAD 语句 |

## 六、待联调事项（尚未完成，如实列出）

1. **HiveServer2 地址/账号未落实**：需要确定用哪台机器的数据源、端口 10000 是否开放；
   填入环境变量后才能真正跑 `CIVIL_AVIATION_SOURCE=hive`。
2. **pyhive / thrift 未在集群客户端安装**：算法切换 Hive 模式前需 `pip install pyhive thrift`。
3. **`load_results.hql` 未在集群执行**：ADS 结果表目前只有建表定义，尚无算法结果数据。
4. **Neo4j 导入**：Cypher 脚本已就绪，尚未在 Neo4j 实例上实际执行并导出节点/边 CSV。
5. **逐机场设计容量仅覆盖 20 个**：其余机场容量缺失，可在后续 ETL 中由成员B 补全，
   接入方式不变（缺值保持 NULL 即可）。

## 七、附件清单

- `hive_ddl/00_create_tables.sql` —— 建表脚本
- `spark_etl/aviation_etl.py` —— ETL 主作业
- `neo4j_import/import_graph.cypher` —— 图导入脚本
- `README.md` —— 运行方式、客流口径、规模差异说明
- `data/processed/hive_load/load_results.hql` —— 算法结果回灌脚本（算法侧生成）
