# -*- coding: utf-8 -*-
"""ODS -> DWD -> DWS -> ADS 民航航线网络数据集构建作业（成员B）。

两种运行方式：
  1) 本地/开发：--source local（默认），自动定位项目根 data/raw 下的
     airports.dat / routes.dat / airport_throughput_2023.csv / airport_capacity_2023.csv，
     先写 ODS 再跑分层加工。
  2) 集群：--source ods，直接读已由采集流程灌好的 ODS 分区，跳过写 ODS。

客流口径（重要，评审请以此为准）：
  公开的 OpenFlights 数据只有「机场年旅客吞吐量」，没有逐航段客流。因此
  dwd_flight_segment.segment_throughput 等指标是**按航段频次分摊的估算值**：
      航段估算客流 = 始发机场年旅客吞吐量 × (该航段航班数 / 该机场出港总航班数)
      total_seat   = 航班数 × AVG_SEATS_PER_FLIGHT（单班次平均座位假设）
      avg_load_factor = min(航段估算客流 / total_seat, 1.0)
  估算值用于支撑「容量流量下钻 / 吞吐量排序」的相对比较，不代表实际售票数据；
  容量饱和预警始终只使用真实吞吐量与真实设计容量，不受估算影响。
"""
import os
from argparse import ArgumentParser
from datetime import date

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F

# 单班次平均座位数：公开数据缺失，采用窄体/宽体混合机队的保守假设值。
# 仅影响 total_seat / avg_load_factor 两个派生估算列，不影响中心性与预警。
AVG_SEATS_PER_FLIGHT = 180

RAW_REQUIRED = ("airports.dat", "routes.dat",
                "airport_throughput_2023.csv", "airport_capacity_2023.csv")


def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="civil_aviation")
    parser.add_argument("--input-root", help="含 raw 文件的目录；缺省时自动向上查找 data/raw")
    parser.add_argument("--source", choices=("local", "ods"), default="local",
                        help="local=从 raw 文件构建(默认)；ods=读集群已有 ODS 分区")
    parser.add_argument("--dt", default=date.today().isoformat())
    return parser.parse_args()


def find_raw_root(explicit=None):
    """定位含四个真实数据文件的 data/raw；优先级：显式参数 > 环境变量 > 逐级向上查找。"""
    candidates = []
    if explicit:
        candidates.append(explicit)
    env = os.environ.get("CIVIL_AVIATION_PROJECT_ROOT")
    if env:
        candidates.append(os.path.join(env, "data", "raw"))
        candidates.append(env)
    here = os.path.dirname(os.path.abspath(__file__))
    cur = here
    for _ in range(8):
        candidates.append(os.path.join(cur, "data", "raw"))
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    for c in candidates:
        c = os.path.abspath(c)
        if all(os.path.isfile(os.path.join(c, f)) for f in RAW_REQUIRED):
            return c
    checked = "\n  ".join(dict.fromkeys(os.path.abspath(c) for c in candidates[:5]))
    raise FileNotFoundError(
        "未找到完整的 raw 数据包（需要 " + ", ".join(RAW_REQUIRED) + "）。"
        "\n已检查：\n  " + checked +
        "\n请用 --input-root 指向项目根 data/raw，或设置 CIVIL_AVIATION_PROJECT_ROOT；"
        "\n若集群 ODS 已就绪，请改用 --source ods。"
    )


def clean_code(column):
    return F.upper(F.trim(F.col(column))).alias(column)


def read_raw(spark, root):
    airports = (
        spark.read.option("header", "false").option("quote", '"')
        .option("escape", '"').csv(f"{root}/airports.dat")
        .toDF("airport_id", "airport_name", "city", "country", "airport_code",
              "icao", "lat", "lng", "altitude", "timezone", "dst",
              "tz_database", "type", "source")
        .select("airport_name", "city", "country", "airport_code", "lat", "lng")
        # OpenFlights 无 province 字段；country 作为上游回退，保证区域子图契约不丢。
        .withColumn("province", F.col("country"))
        .withColumn("lat", F.col("lat").cast("double"))
        .withColumn("lng", F.col("lng").cast("double"))
        .filter(F.col("airport_code").isNotNull() & (F.length("airport_code") == 3))
        .withColumn("airport_code", clean_code("airport_code"))
    )
    routes = (
        spark.read.option("header", "false").option("quote", '"')
        .option("escape", '"').csv(f"{root}/routes.dat")
        .toDF("airline", "airline_id", "from_airport_code", "from_id",
              "to_airport_code", "to_id", "codeshare", "stops", "equipment")
        .select("from_airport_code", "to_airport_code")
        .withColumn("from_airport_code", clean_code("from_airport_code"))
        .withColumn("to_airport_code", clean_code("to_airport_code"))
        .filter((F.length("from_airport_code") == 3) &
                (F.length("to_airport_code") == 3) &
                (F.col("from_airport_code") != F.col("to_airport_code")))
    )
    throughput = (
        spark.read.option("header", "true").option("encoding", "UTF-8")
        .csv(f"{root}/airport_throughput_2023.csv")
        .select(F.upper(F.trim("iata_code")).alias("airport_code"),
                F.col("airport_name_cn").alias("airport_name"),
                F.lit(2023).alias("stat_year"),
                F.col("annual_passengers_2023").cast("long").alias("passenger_throughput"),
                "country")
    )
    capacity = (
        spark.read.option("header", "true").option("encoding", "UTF-8")
        .csv(f"{root}/airport_capacity_2023.csv")
        .select(F.upper(F.trim("iata_code")).alias("airport_code"),
                F.col("airport_name"),
                F.col("design_capacity_pax").cast("long").alias("designed_capacity"),
                F.lit(2023).alias("capacity_year"), "country")
    )
    return airports, routes, throughput, capacity


def read_ods(spark, database, dt):
    base = f"{database}."
    airports = spark.table(base + "ods_airport_info").where(F.col("dt") == dt).drop("dt")
    routes = spark.table(base + "ods_flight_schedule").where(F.col("dt") == dt)
    throughput = spark.table(base + "ods_airport_throughput").where(F.col("dt") == dt).drop("dt")
    capacity = spark.table(base + "ods_airport_capacity").where(F.col("dt") == dt).drop("dt")
    return airports, routes, throughput, capacity


def write_ods(data, database, dt):
    """写 ODS。insertInto 按「位置」匹配列，select 顺序必须与 DDL 完全一致。

    分区表覆盖：main() 已开启动态分区覆盖，仅替换本次 dt 分区，不动历史分区。
    """
    airports, routes, throughput, capacity = data
    airports.select("airport_code", "airport_name", "city", "country", "province",
                    "lat", "lng").withColumn("dt", F.lit(dt)).write.mode(
        "overwrite").insertInto(f"{database}.ods_airport_info")
    throughput.select("airport_code", "airport_name", "country", "stat_year",
                      "passenger_throughput").withColumn("dt", F.lit(dt)).write.mode(
        "overwrite").insertInto(f"{database}.ods_airport_throughput")
    capacity.select("airport_code", "airport_name", "country", "designed_capacity",
                    "capacity_year").withColumn("dt", F.lit(dt)).write.mode(
        "overwrite").insertInto(f"{database}.ods_airport_capacity")
    # 航段是边源，每个 (from,to) 生成一行合成计划即可，航班级明细非本课题范围。
    routes.select("from_airport_code", "to_airport_code").withColumn(
        "flight_no", F.lit(None).cast("string")).withColumn(
        "dep_time", F.lit(None).cast("string")).withColumn(
        "arr_time", F.lit(None).cast("string")).withColumn(
        "aircraft_type", F.lit(None).cast("string")).withColumn(
        "seat_count", F.lit(None).cast("int")).withColumn(
        "flight_date", F.lit(None).cast("string")).withColumn("dt", F.lit(dt)
    ).select("flight_no", "from_airport_code", "to_airport_code", "dep_time",
             "arr_time", "aircraft_type", "seat_count", "flight_date", "dt"
    ).write.mode("overwrite").insertInto(f"{database}.ods_flight_schedule")


def build(spark, data, database, dt):
    airports, routes, throughput, capacity = data
    airport_w = Window.partitionBy("airport_code").orderBy(F.desc("stat_year"))
    throughput = (throughput.withColumn("_rn", F.row_number().over(airport_w))
                  .where("_rn = 1").drop("_rn"))
    capacity_w = Window.partitionBy("airport_code").orderBy(F.desc("capacity_year"))
    capacity = (capacity.withColumn("_rn", F.row_number().over(capacity_w))
                .where("_rn = 1").drop("_rn"))

    airport_dwd = (
        airports
        .join(throughput.select("airport_code", "passenger_throughput"),
              "airport_code", "left")
        .join(capacity.select("airport_code", "designed_capacity"), "airport_code", "left")
        .withColumn("annual_throughput", F.coalesce("passenger_throughput", F.lit(0)).cast("long"))
        .withColumn("capacity_ratio", F.when(F.col("designed_capacity") > 0,
                                             F.col("annual_throughput") / F.col("designed_capacity"))
                                      .otherwise(F.lit(0.0)))
        .select("airport_code", "airport_name", "city", "country", "province",
                "lat", "lng", "annual_throughput", "designed_capacity", "capacity_ratio")
        .withColumn("dt", F.lit(dt))
    )
    airport_dwd.write.mode("overwrite").insertInto(f"{database}.dwd_airport")

    base_dwd = airport_dwd.drop("dt")
    valid_codes = airports.select("airport_code").distinct()
    segments = (
        routes.join(valid_codes.withColumnRenamed("airport_code", "src"),
                    F.col("from_airport_code") == F.col("src"))
        .join(valid_codes.withColumnRenamed("airport_code", "dst"),
              F.col("to_airport_code") == F.col("dst"))
        .groupBy("from_airport_code", "to_airport_code")
        .agg(F.count("*").cast("int").alias("flight_count"))
    )

    # ---- 按航段频次分摊真实机场吞吐量，得到可核查的估算客流（口径见文件头） ----
    out_total = (segments.groupBy("from_airport_code")
                 .agg(F.sum("flight_count").alias("_out_total")))
    src_metric = base_dwd.select(
        F.col("airport_code").alias("from_airport_code"),
        "annual_throughput", "designed_capacity", "capacity_ratio")
    dst_metric = base_dwd.select(
        F.col("airport_code").alias("to_airport_code"),
        F.col("capacity_ratio").alias("_dst_capacity_ratio"))
    seg_full = (
        segments.join(out_total, "from_airport_code")
        .join(src_metric, "from_airport_code", "left")
        .join(dst_metric, "to_airport_code", "left")
        .withColumn("segment_throughput",
                    F.when(F.col("_out_total") > 0,
                           F.round(F.coalesce(F.col("annual_throughput"), F.lit(0))
                                   * F.col("flight_count") / F.col("_out_total")))
                     .otherwise(F.lit(0)).cast("long"))
        .withColumn("total_seat", (F.col("flight_count")
                                   * F.lit(AVG_SEATS_PER_FLIGHT)).cast("int"))
        .withColumn("avg_load_factor",
                    F.when(F.col("total_seat") > 0,
                           F.least(F.lit(1.0),
                                   F.col("segment_throughput") / F.col("total_seat")))
                     .otherwise(F.lit(0.0)).cast("double"))
        .withColumn("_seg_capacity_ratio",
                    F.greatest(F.coalesce(F.col("capacity_ratio"), F.lit(0.0)),
                               F.coalesce(F.col("_dst_capacity_ratio"), F.lit(0.0))))
    )
    seg_full.select("from_airport_code", "to_airport_code", "flight_count",
                    "total_seat", "avg_load_factor", "segment_throughput").withColumn(
        "dt", F.lit(dt)).write.mode("overwrite").insertInto(
        f"{database}.dwd_flight_segment")

    route_stat = (
        seg_full.select(
            "from_airport_code", "to_airport_code", "flight_count",
            F.col("segment_throughput").alias("passenger_volume"),
            F.col("segment_throughput").alias("route_throughput"),
            F.col("avg_load_factor").alias("load_factor"),
            F.col("_seg_capacity_ratio").alias("capacity_utilization"))
        .withColumn("dt", F.lit(dt))
    )
    route_stat.write.mode("overwrite").insertInto(f"{database}.dws_route_stat")

    degree_out = segments.groupBy("from_airport_code").agg(
        F.sum("flight_count").alias("degree_out"))
    degree_in = segments.groupBy("to_airport_code").agg(
        F.sum("flight_count").alias("degree_in"))
    airport_stat = (
        base_dwd.join(degree_out, F.col("airport_code") == F.col("from_airport_code"), "left")
        .join(degree_in, F.col("airport_code") == F.col("to_airport_code"), "left")
        .fillna(0, ["degree_in", "degree_out"])
        .withColumn("total_degree", F.col("degree_in") + F.col("degree_out"))
        .select("airport_code",
                F.col("degree_in").cast("int").alias("degree_in"),
                F.col("degree_out").cast("int").alias("degree_out"),
                F.col("total_degree").cast("int").alias("total_degree"),
                F.col("annual_throughput").alias("passenger_throughput"),
                "designed_capacity", F.col("capacity_ratio").alias("capacity_utilization"))
        .withColumn("dt", F.lit(dt))
    )
    airport_stat.write.mode("overwrite").insertInto(f"{database}.dws_airport_stat")

    (airport_dwd.withColumn("node_weight",
                            F.col("annual_throughput").cast("double"))
     .select("airport_code", "airport_name", "city", "country", "province",
             "lat", "lng", "annual_throughput", "designed_capacity",
             "capacity_ratio", "node_weight", "dt")
     .write.mode("overwrite").insertInto(f"{database}.ads_graph_node"))
    (route_stat.select("from_airport_code", "to_airport_code",
                       F.when(F.col("route_throughput") > 0,
                              F.col("route_throughput").cast("double"))
                        .otherwise(F.col("flight_count").cast("double")).alias("edge_weight"),
                       "flight_count", "route_throughput", "dt")
     .write.mode("overwrite").insertInto(f"{database}.ads_graph_edge"))


def main():
    args = parse_args()
    spark = (SparkSession.builder.appName("civil-aviation-graph-etl")
             .enableHiveSupport().getOrCreate())
    # 分区表只覆盖本次 dt，避免 overwrite 误删历史分区；同时兼容分桶表 insertInto。
    spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
    spark.conf.set("hive.exec.dynamic.partition.mode", "nonstrict")
    spark.sql(f"CREATE DATABASE IF NOT EXISTS {args.database}")

    if args.source == "local":
        root = find_raw_root(args.input_root)
        print(f"[ETL] raw 数据目录：{root}")
        write_ods(read_raw(spark, root), args.database, args.dt)
        data = read_ods(spark, args.database, args.dt)
    else:
        print(f"[ETL] 读取已有 ODS 分区 dt={args.dt}")
        data = read_ods(spark, args.database, args.dt)

    build(spark, data, args.database, args.dt)
    for table in ("ads_graph_node", "ads_graph_edge"):
        n = spark.sql(f"SELECT COUNT(*) AS n FROM {args.database}.{table} "
                      f"WHERE dt='{args.dt}'").collect()[0]["n"]
        print(f"[ETL] {table} dt={args.dt}: {n} 行")
    spark.stop()


if __name__ == "__main__":
    main()
