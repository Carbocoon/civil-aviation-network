"""Build the ODS -> DWD -> DWS -> ADS aviation graph data set.

The job accepts the repository's raw files for development and can instead
read an existing Hive ODS when ``--input-root`` is omitted.
"""
from argparse import ArgumentParser
from datetime import date

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("--database", default="civil_aviation")
    parser.add_argument("--input-root", help="Directory containing raw/ files")
    parser.add_argument("--dt", default=date.today().isoformat())
    return parser.parse_args()


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
        # OpenFlights has no province field; country is the safest source-level
        # fallback and preserves the country-based regional graph contract.
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
    airports, routes, throughput, capacity = data
    airports.select("airport_code", "airport_name", "city", "country", "province",
                    "lat", "lng").withColumn("dt", F.lit(dt)).write.mode("overwrite").insertInto(
        f"{database}.ods_airport_info")
    throughput.select("airport_code", "airport_name", "country", "stat_year",
                      "passenger_throughput").withColumn("dt", F.lit(dt)).write.mode("overwrite").insertInto(
        f"{database}.ods_airport_throughput")
    capacity.select("airport_code", "airport_name", "country", "designed_capacity",
                    "capacity_year").withColumn("dt", F.lit(dt)).write.mode("overwrite").insertInto(
        f"{database}.ods_airport_capacity")
    # Routes are an edge source, so one synthetic schedule row per route is enough.
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
        airports                .join(throughput.select("airport_code", "passenger_throughput"),
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

    valid_codes = airports.select("airport_code").distinct()
    segments = (
        routes.join(valid_codes.withColumnRenamed("airport_code", "src"), F.col("from_airport_code") == F.col("src"))
        .join(valid_codes.withColumnRenamed("airport_code", "dst"), F.col("to_airport_code") == F.col("dst"))
        .groupBy("from_airport_code", "to_airport_code")
        .agg(F.count("*").cast("int").alias("flight_count"))
        .withColumn("total_seat", F.lit(0).cast("int"))
        .withColumn("avg_load_factor", F.lit(0.0))
        .withColumn("segment_throughput", F.lit(0).cast("long"))
        .withColumn("dt", F.lit(dt))
    )
    segments.write.mode("overwrite").insertInto(f"{database}.dwd_flight_segment")

    route_stat = (segments.drop("dt")
        .withColumn("passenger_volume", F.col("segment_throughput"))
        .withColumn("route_throughput", F.col("segment_throughput"))
        .withColumn("load_factor", F.col("avg_load_factor"))
        .withColumn("capacity_utilization", F.lit(0.0))
        .select("from_airport_code", "to_airport_code", "flight_count",
                "passenger_volume", "route_throughput", "load_factor",
                "capacity_utilization")
        .withColumn("dt", F.lit(dt)))
    route_stat.write.mode("overwrite").insertInto(f"{database}.dws_route_stat")

    degree_out = segments.groupBy("from_airport_code").count().withColumnRenamed("count", "degree_out")
    degree_in = segments.groupBy("to_airport_code").count().withColumnRenamed("count", "degree_in")
    airport_stat = (airport_dwd.drop("dt").join(degree_out, F.col("airport_code") == F.col("from_airport_code"), "left")
        .join(degree_in, F.col("airport_code") == F.col("to_airport_code"), "left")
        .fillna(0, ["degree_in", "degree_out"])
        .withColumn("total_degree", F.col("degree_in") + F.col("degree_out"))
        .select("airport_code", "degree_in", "degree_out", "total_degree",
                F.col("annual_throughput").alias("passenger_throughput"),
                "designed_capacity", F.col("capacity_ratio").alias("capacity_utilization"))
        .withColumn("dt", F.lit(dt)))
    airport_stat.write.mode("overwrite").insertInto(f"{database}.dws_airport_stat")

    (airport_dwd.withColumn("node_weight",
                            F.col("annual_throughput").cast("double"))
     .select("airport_code", "airport_name", "city", "country", "province",
             "lat", "lng", "annual_throughput", "designed_capacity",
             "capacity_ratio", F.col("node_weight").cast("double").alias("node_weight"),
             "dt")
     .write.mode("overwrite").insertInto(f"{database}.ads_graph_node"))
    (route_stat.select("from_airport_code", "to_airport_code",
                       F.when(F.col("route_throughput") > 0, F.col("route_throughput"))
                        .otherwise(F.col("flight_count")).cast("double").alias("edge_weight"),
                      "flight_count", "route_throughput", "dt")
     .write.mode("overwrite").insertInto(f"{database}.ads_graph_edge"))


def main():
    args = parse_args()
    spark = (SparkSession.builder.appName("civil-aviation-graph-etl")
             .enableHiveSupport().getOrCreate())
    spark.sql(f"CREATE DATABASE IF NOT EXISTS {args.database}")
    data = read_raw(spark, args.input_root) if args.input_root else read_ods(
        spark, args.database, args.dt)
    if args.input_root:
        write_ods(data, args.database, args.dt)
        data = read_ods(spark, args.database, args.dt)
    build(spark, data, args.database, args.dt)
    spark.stop()


if __name__ == "__main__":
    main()
