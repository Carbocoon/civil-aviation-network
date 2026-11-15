-- 算法结果回灌 ADS 层（由 algorithm/hive_writer.py 自动生成）
-- 生成时间：2026-11-15 09:37:09  分区 dt=2026-11-15
-- 用法：把本目录（5 个 CSV + 本脚本）整体拷到 Hive 节点，在该目录下执行：
--   hive -f load_results.hql
-- 注意：ADS 结果表按设计是 ORC + Snappy，而算法导出的是不带表头的 CSV；
--   Hive 的 LOAD DATA 只搬文件不做格式转换，因此先 LOAD 到 TEXTFILE 临时表，
--   再 INSERT ... SELECT 由 Hive 转成 ORC 写入目标分区。
USE civil_aviation;

-- ads_centrality_result: 7968 行
DROP TABLE IF EXISTS tmp_ads_centrality_result;
CREATE TABLE tmp_ads_centrality_result (
  airport_code STRING,
  degree_centrality DOUBLE,
  closeness_centrality DOUBLE,
  betweenness_centrality DOUBLE,
  pagerank DOUBLE,
  calc_time STRING
) ROW FORMAT DELIMITED FIELDS TERMINATED BY ',' STORED AS TEXTFILE;
LOAD DATA LOCAL INPATH 'centrality_result.csv' OVERWRITE INTO TABLE tmp_ads_centrality_result;
INSERT OVERWRITE TABLE ads_centrality_result PARTITION (dt='2026-11-15')
SELECT airport_code, degree_centrality, closeness_centrality, betweenness_centrality, pagerank, calc_time FROM tmp_ads_centrality_result;
DROP TABLE tmp_ads_centrality_result;

-- ads_coupling_index: 7968 行
DROP TABLE IF EXISTS tmp_ads_coupling_index;
CREATE TABLE tmp_ads_coupling_index (
  airport_code STRING,
  coupling_index DOUBLE,
  alpha DOUBLE,
  beta DOUBLE,
  calc_time STRING
) ROW FORMAT DELIMITED FIELDS TERMINATED BY ',' STORED AS TEXTFILE;
LOAD DATA LOCAL INPATH 'coupling_index.csv' OVERWRITE INTO TABLE tmp_ads_coupling_index;
INSERT OVERWRITE TABLE ads_coupling_index PARTITION (dt='2026-11-15')
SELECT airport_code, coupling_index, alpha, beta, calc_time FROM tmp_ads_coupling_index;
DROP TABLE tmp_ads_coupling_index;

-- ads_bottleneck_result: 40014 行
DROP TABLE IF EXISTS tmp_ads_bottleneck_result;
CREATE TABLE tmp_ads_bottleneck_result (
  from_airport_code STRING,
  to_airport_code STRING,
  bottleneck_score DOUBLE,
  rank INT,
  calc_time STRING
) ROW FORMAT DELIMITED FIELDS TERMINATED BY ',' STORED AS TEXTFILE;
LOAD DATA LOCAL INPATH 'bottleneck_result.csv' OVERWRITE INTO TABLE tmp_ads_bottleneck_result;
INSERT OVERWRITE TABLE ads_bottleneck_result PARTITION (dt='2026-11-15')
SELECT from_airport_code, to_airport_code, bottleneck_score, rank, calc_time FROM tmp_ads_bottleneck_result;
DROP TABLE tmp_ads_bottleneck_result;

-- ads_vulnerability_index: 8 行
DROP TABLE IF EXISTS tmp_ads_vulnerability_index;
CREATE TABLE tmp_ads_vulnerability_index (
  scenario_id STRING,
  removed_nodes INT,
  connectivity_loss DOUBLE,
  vulnerability_score DOUBLE,
  calc_time STRING
) ROW FORMAT DELIMITED FIELDS TERMINATED BY ',' STORED AS TEXTFILE;
LOAD DATA LOCAL INPATH 'vulnerability_index.csv' OVERWRITE INTO TABLE tmp_ads_vulnerability_index;
INSERT OVERWRITE TABLE ads_vulnerability_index PARTITION (dt='2026-11-15')
SELECT scenario_id, removed_nodes, connectivity_loss, vulnerability_score, calc_time FROM tmp_ads_vulnerability_index;
DROP TABLE tmp_ads_vulnerability_index;

-- ads_saturation_warning: 10 行
DROP TABLE IF EXISTS tmp_ads_saturation_warning;
CREATE TABLE tmp_ads_saturation_warning (
  airport_code STRING,
  capacity_utilization DOUBLE,
  warning_level INT,
  threshold_t1 DOUBLE,
  threshold_t2 DOUBLE,
  warn_time STRING
) ROW FORMAT DELIMITED FIELDS TERMINATED BY ',' STORED AS TEXTFILE;
LOAD DATA LOCAL INPATH 'saturation_warning.csv' OVERWRITE INTO TABLE tmp_ads_saturation_warning;
INSERT OVERWRITE TABLE ads_saturation_warning PARTITION (dt='2026-11-15')
SELECT airport_code, capacity_utilization, warning_level, threshold_t1, threshold_t2, warn_time FROM tmp_ads_saturation_warning;
DROP TABLE tmp_ads_saturation_warning;

-- 更新统计信息，便于 Spark SQL / Hive 优化执行计划
ANALYZE TABLE ads_centrality_result PARTITION (dt='2026-11-15') COMPUTE STATISTICS;
ANALYZE TABLE ads_coupling_index PARTITION (dt='2026-11-15') COMPUTE STATISTICS;
ANALYZE TABLE ads_bottleneck_result PARTITION (dt='2026-11-15') COMPUTE STATISTICS;
ANALYZE TABLE ads_vulnerability_index PARTITION (dt='2026-11-15') COMPUTE STATISTICS;
ANALYZE TABLE ads_saturation_warning PARTITION (dt='2026-11-15') COMPUTE STATISTICS;
