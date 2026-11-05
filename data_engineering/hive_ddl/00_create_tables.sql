-- 民航航线网络数仓建表脚本。
-- 执行前可通过 hive --hivevar database=civil_aviation 传入目标库。
CREATE DATABASE IF NOT EXISTS ${hivevar:database};
USE ${hivevar:database};

CREATE TABLE IF NOT EXISTS ods_flight_schedule (
  flight_no STRING, from_airport_code STRING, to_airport_code STRING,
  dep_time STRING, arr_time STRING, aircraft_type STRING,
  seat_count INT, flight_date STRING
) PARTITIONED BY (dt STRING)
STORED AS ORC TBLPROPERTIES ('orc.compress'='SNAPPY');

CREATE TABLE IF NOT EXISTS ods_airport_info (
  airport_code STRING, airport_name STRING, city STRING, country STRING,
  province STRING, lat DOUBLE, lng DOUBLE
) PARTITIONED BY (dt STRING)
STORED AS ORC TBLPROPERTIES ('orc.compress'='SNAPPY');

CREATE TABLE IF NOT EXISTS ods_airport_throughput (
  airport_code STRING, airport_name STRING, country STRING,
  stat_year INT, passenger_throughput BIGINT
) PARTITIONED BY (dt STRING)
STORED AS ORC TBLPROPERTIES ('orc.compress'='SNAPPY');

CREATE TABLE IF NOT EXISTS ods_airport_capacity (
  airport_code STRING, airport_name STRING, country STRING,
  designed_capacity BIGINT, capacity_year INT
) PARTITIONED BY (dt STRING)
STORED AS ORC TBLPROPERTIES ('orc.compress'='SNAPPY');

CREATE TABLE IF NOT EXISTS dwd_airport (
  airport_code STRING, airport_name STRING, city STRING, country STRING,
  province STRING, lat DOUBLE, lng DOUBLE, annual_throughput BIGINT,
  designed_capacity BIGINT, capacity_ratio DOUBLE
) PARTITIONED BY (dt STRING)
CLUSTERED BY (airport_code) INTO 8 BUCKETS
STORED AS ORC TBLPROPERTIES ('orc.compress'='SNAPPY');

CREATE TABLE IF NOT EXISTS dwd_flight_segment (
  from_airport_code STRING, to_airport_code STRING, flight_count INT,
  total_seat INT, avg_load_factor DOUBLE, segment_throughput BIGINT
) PARTITIONED BY (dt STRING)
CLUSTERED BY (from_airport_code) INTO 8 BUCKETS
STORED AS ORC TBLPROPERTIES ('orc.compress'='SNAPPY');

CREATE TABLE IF NOT EXISTS dws_airport_stat (
  airport_code STRING, degree_in INT, degree_out INT, total_degree INT,
  passenger_throughput BIGINT, designed_capacity BIGINT,
  capacity_utilization DOUBLE
) PARTITIONED BY (dt STRING)
STORED AS ORC TBLPROPERTIES ('orc.compress'='SNAPPY');

CREATE TABLE IF NOT EXISTS dws_route_stat (
  from_airport_code STRING, to_airport_code STRING, flight_count INT,
  passenger_volume BIGINT, route_throughput BIGINT, load_factor DOUBLE,
  capacity_utilization DOUBLE
) PARTITIONED BY (dt STRING)
CLUSTERED BY (from_airport_code) INTO 8 BUCKETS
STORED AS ORC TBLPROPERTIES ('orc.compress'='SNAPPY');

CREATE TABLE IF NOT EXISTS ads_graph_node (
  airport_code STRING, airport_name STRING, city STRING, country STRING,
  province STRING, lat DOUBLE, lng DOUBLE, annual_throughput BIGINT,
  designed_capacity BIGINT, capacity_ratio DOUBLE, node_weight DOUBLE
) PARTITIONED BY (dt STRING)
CLUSTERED BY (airport_code) INTO 8 BUCKETS
STORED AS ORC TBLPROPERTIES ('orc.compress'='SNAPPY');

CREATE TABLE IF NOT EXISTS ads_graph_edge (
  from_airport_code STRING, to_airport_code STRING, edge_weight DOUBLE,
  flight_count INT, route_throughput BIGINT
) PARTITIONED BY (dt STRING)
CLUSTERED BY (from_airport_code) INTO 8 BUCKETS
STORED AS ORC TBLPROPERTIES ('orc.compress'='SNAPPY');

CREATE TABLE IF NOT EXISTS ads_centrality_result (
  airport_code STRING, degree_centrality DOUBLE, closeness_centrality DOUBLE,
  betweenness_centrality DOUBLE, pagerank DOUBLE, calc_time STRING
) PARTITIONED BY (dt STRING)
STORED AS ORC TBLPROPERTIES ('orc.compress'='SNAPPY');

CREATE TABLE IF NOT EXISTS ads_coupling_index (
  airport_code STRING, coupling_index DOUBLE, alpha DOUBLE, beta DOUBLE,
  calc_time STRING
) PARTITIONED BY (dt STRING)
STORED AS ORC TBLPROPERTIES ('orc.compress'='SNAPPY');

CREATE TABLE IF NOT EXISTS ads_bottleneck_result (
  from_airport_code STRING, to_airport_code STRING, bottleneck_score DOUBLE,
  rank INT, calc_time STRING
) PARTITIONED BY (dt STRING)
STORED AS ORC TBLPROPERTIES ('orc.compress'='SNAPPY');

CREATE TABLE IF NOT EXISTS ads_vulnerability_index (
  scenario_id STRING, removed_nodes INT, connectivity_loss DOUBLE,
  vulnerability_score DOUBLE, calc_time STRING
) PARTITIONED BY (dt STRING)
STORED AS ORC TBLPROPERTIES ('orc.compress'='SNAPPY');

CREATE TABLE IF NOT EXISTS ads_saturation_warning (
  airport_code STRING, capacity_utilization DOUBLE, warning_level INT,
  threshold_t1 DOUBLE, threshold_t2 DOUBLE, warn_time STRING
) PARTITIONED BY (dt STRING)
STORED AS ORC TBLPROPERTIES ('orc.compress'='SNAPPY');

-- ADS 结果表由算法写入。每批 ETL 完成后再执行：
-- ANALYZE TABLE ads_graph_node PARTITION (dt='${hivevar:dt}') COMPUTE STATISTICS;
-- ANALYZE TABLE ads_graph_edge PARTITION (dt='${hivevar:dt}') COMPUTE STATISTICS;
