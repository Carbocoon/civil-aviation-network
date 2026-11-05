# 数据工程（2313040123段亦弢）

本目录负责民航航线网络的数据入仓、ETL 和图数据库导入，数据链路如下：

```text
data/raw
  -> ODS（原始层）
  -> DWD（清洗明细层）
  -> DWS（机场/航段汇总层）
  -> ADS（算法图节点/边）
  -> NetworkX / Neo4j / 可视化
```

## 目录与文件

```text
data_engineering/
├── hive_ddl/
│   └── 00_create_tables.sql     # ODS、DWD、DWS、ADS 建表
├── spark_etl/
│   └── aviation_etl.py          # Spark ETL 主作业
└── neo4j_import/
    └── import_graph.cypher      # Neo4j 节点和航线导入
```

### `hive_ddl/`

[00_create_tables.sql](hive_ddl/00_create_tables.sql) 创建完整数仓表：

- ODS：航班计划、机场信息、吞吐量、设计容量；
- DWD：机场明细和有向航段明细；
- DWS：机场统计和航段统计；
- ADS：`ads_graph_node`、`ads_graph_edge` 以及算法结果表。

表统一使用 ORC + Snappy，按 `dt` 分区；图节点、图边和航段统计表按机场
代码分桶。`ads_graph_node` 保留 `country`，节点 ID 使用 IATA 三字码。

### `spark_etl/`

[aviation_etl.py](spark_etl/aviation_etl.py) 是 PySpark 主作业，支持两种输入模式：

1. 传入 `--input-root`：读取 `data/raw`，先写入 ODS，再从 ODS 继续完成
   DWD → DWS → ADS；
2. 不传 `--input-root`：读取指定数据库和 `dt` 分区中已存在的 ODS 数据。

主要处理内容：

- 清洗机场代码、经纬度和数值字段；
- 聚合航线为有向航段；
- 计算机场度数、吞吐量和容量利用率；
- 生成算法直接读取的 `ads_graph_node` / `ads_graph_edge`。

缺少设计容量的机场保持 `NULL`，其容量利用率按 0 处理，不使用虚构容量。

### `neo4j_import/`

[import_graph.cypher](neo4j_import/import_graph.cypher) 从 ADS 导出的 CSV
导入 Neo4j：

- 创建 `Airport.airport_code` 唯一约束；
- 创建机场代码索引；
- 幂等导入机场节点；
- 幂等导入 `(:Airport)-[:ROUTE]->(:Airport)` 航线关系。

## 运行环境

本地运行需要：

- Java；
- Apache Spark；
- Python 3.10+（Spark 4.x 推荐 Python 3.11）；
- `data/raw` 原始数据文件。

如果使用项目中的 Python 3.11 虚拟环境，先执行：

```bash
source .venv311/bin/activate
export PYSPARK_PYTHON="$PWD/.venv311/bin/python"
export PYSPARK_DRIVER_PYTHON="$PWD/.venv311/bin/python"
```

## 运行 ETL

在仓库根目录执行。首次运行先建表：

```bash
spark-sql \
  --hivevar database=civil_aviation \
  --hivevar dt=2023-12-31 \
  -f data_engineering/hive_ddl/00_create_tables.sql
```

然后执行 Spark ETL：

```bash
spark-submit \
  data_engineering/spark_etl/aviation_etl.py \
  --database civil_aviation \
  --input-root data/raw \
  --dt 2023-12-31
```

也可以直接读取已经入仓的 ODS：

```bash
spark-submit \
  data_engineering/spark_etl/aviation_etl.py \
  --database civil_aviation \
  --dt 2023-12-31
```

## 已验证结果

本地 Spark 4.3.0、Python 3.11 环境下，`2023-12-31` 分区 ETL 成功完成：

```text
ads_graph_node   6072
ads_graph_edge  37041
dwd_airport      6072
dws_route_stat  37041
```

可使用以下命令核验：

```bash
spark-sql --database civil_aviation -e "
SELECT 'ads_graph_node', COUNT(*) FROM ads_graph_node
WHERE dt='2023-12-31'
UNION ALL
SELECT 'ads_graph_edge', COUNT(*) FROM ads_graph_edge
WHERE dt='2023-12-31';
"
```

## Neo4j 导入

先将 ADS 最新分区导出为带表头的 CSV，再执行：

```bash
cypher-shell -d neo4j \
  --param 'nodes_file=>"file:///ads_graph_node.csv"' \
  --param 'edges_file=>"file:///ads_graph_edge.csv"' \
  -f data_engineering/neo4j_import/import_graph.cypher
```

生产环境若使用 HiveServer2，需要额外提供地址、账号和数据库配置，并在
算法侧实现 Hive 读取；本目录的本地 Spark ETL 不依赖 Hive CLI。
