# -*- coding: utf-8 -*-
"""把算法结果整理成 Hive ADS 结果表可加载的文件 + HQL 脚本。

本地模式也能执行：在 data/processed/hive_load/ 下生成 5 个列序与 DDL 一致的 CSV
和一份 load_results.hql。集群上把该目录拷到 Hive 节点后执行 HQL，即可把中心性、
耦合、瓶颈、脆弱性、容量饱和预警结果回灌 ADS 层，形成「Hive 取数 → 算法 → Hive 落库」闭环。

字段对应关系见 docs/algorithm_api.md。
"""
import csv
import os
from datetime import datetime

from . import config

# (结果表, CSV文件名, DDL列顺序)  —— 与 data_engineering/hive_ddl/00_create_tables.sql 一致
TABLE_SPECS = (
    ("ads_centrality_result", "centrality_result.csv",
     ["airport_code", "degree_centrality", "closeness_centrality",
      "betweenness_centrality", "pagerank", "calc_time"]),
    ("ads_coupling_index", "coupling_index.csv",
     ["airport_code", "coupling_index", "alpha", "beta", "calc_time"]),
    ("ads_bottleneck_result", "bottleneck_result.csv",
     ["from_airport_code", "to_airport_code", "bottleneck_score", "rank", "calc_time"]),
    ("ads_vulnerability_index", "vulnerability_index.csv",
     ["scenario_id", "removed_nodes", "connectivity_loss",
      "vulnerability_score", "calc_time"]),
    ("ads_saturation_warning", "saturation_warning.csv",
     ["airport_code", "capacity_utilization", "warning_level",
      "threshold_t1", "threshold_t2", "warn_time"]),
)

# 与 DDL（data_engineering/hive_ddl/00_create_tables.sql）一致的列类型。
# 结果表是 ORC，而算法导出的是 CSV：Hive 的 LOAD DATA 只搬文件、不做格式转换，
# 直接 LOAD 进 ORC 表会导致读表时报「不是合法 ORC 文件」或读到 0 行。
# 因此回灌脚本先用 TEXTFILE 临时表接住 CSV，再 INSERT ... SELECT 由 Hive 转成 ORC。
TABLE_COLUMN_TYPES = {
    "ads_centrality_result": ["STRING", "DOUBLE", "DOUBLE", "DOUBLE", "DOUBLE", "STRING"],
    "ads_coupling_index": ["STRING", "DOUBLE", "DOUBLE", "DOUBLE", "STRING"],
    "ads_bottleneck_result": ["STRING", "STRING", "DOUBLE", "INT", "STRING"],
    "ads_vulnerability_index": ["STRING", "INT", "DOUBLE", "DOUBLE", "STRING"],
    "ads_saturation_warning": ["STRING", "DOUBLE", "INT", "DOUBLE", "DOUBLE", "STRING"],
}


def _safe(v):
    """CSV 里的空值统一写成空串，字符串里的逗号由 csv 模块处理。"""
    return "" if v is None else v


def build_rows(global_res, china_res=None):
    """把 run_analysis 的结果整理成 {表名: [dict行]}。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    res_list = [r for r in (global_res, china_res) if r is not None]

    airport_rows = []
    for res in res_list:
        airport_rows.extend(res.get("airport_rows", []))
    # 节点 ID -> IATA（本地模式为数字 ID，Hive 模式本身即 IATA）
    id2iata = {str(r["airport_id"]): (r.get("iata") or str(r["airport_id"]))
               for r in airport_rows}

    max_deg = max((float(r.get("w_degree") or 0) for r in airport_rows), default=0) or 1.0

    centrality, coupling = [], []
    for r in airport_rows:
        code = r.get("iata") or str(r["airport_id"])
        centrality.append({
            "airport_code": code,
            "degree_centrality": round(float(r.get("w_degree") or 0) / max_deg, 6),
            "closeness_centrality": r.get("closeness", ""),
            "betweenness_centrality": r.get("betweenness", ""),
            "pagerank": r.get("pagerank", ""),
            "calc_time": now,
        })
        coupling.append({
            "airport_code": code,
            "coupling_index": r.get("coupling", ""),
            "alpha": config.ALPHA,
            "beta": config.BETA,
            "calc_time": now,
        })

    bottleneck = []
    rank = 0
    for res in res_list:
        for e in res.get("edge_rows", []):
            rank += 1
            bottleneck.append({
                "from_airport_code": id2iata.get(str(e.get("src_id")), e.get("src_id")),
                "to_airport_code": id2iata.get(str(e.get("dst_id")), e.get("dst_id")),
                "bottleneck_score": e.get("bottleneck", ""),
                "rank": rank,
                "calc_time": now,
            })

    vuln = []
    for res in res_list:
        for item in res.get("vuln_by_k", []):
            loss = item.get("lcc_drop_ratio", 0)
            vuln.append({
                "scenario_id": f"{res['label']}_topk_{item.get('k')}",
                "removed_nodes": item.get("removed", item.get("k")),
                "connectivity_loss": round(loss, 6),
                "vulnerability_score": round(loss, 6),
                "calc_time": now,
            })

    warnings_rows = []
    for res in res_list:
        for w in res.get("warnings_rows", []):
            warnings_rows.append({
                "airport_code": w.get("iata") or id2iata.get(str(w.get("airport_id")), ""),
                "capacity_utilization": w.get("utilization", ""),
                "warning_level": w.get("level", ""),
                "threshold_t1": config.TAU1,
                "threshold_t2": config.TAU2,
                "warn_time": now,
            })

    return {
        "ads_centrality_result": centrality,
        "ads_coupling_index": coupling,
        "ads_bottleneck_result": bottleneck,
        "ads_vulnerability_index": vuln,
        "ads_saturation_warning": warnings_rows,
    }


def write_load_script(global_res, china_res=None, dt=None, out_dir=None):
    """生成 CSV + HQL，返回 (输出目录, HQL路径, {表名: 行数})。"""
    dt = dt or config.HIVE_RESULT_DT or datetime.now().strftime("%Y-%m-%d")
    out_dir = out_dir or os.path.join(config.DATA_PROC_DIR, "hive_load")
    os.makedirs(out_dir, exist_ok=True)
    db = config.HIVE_CONFIG.get("database") or "civil_aviation"
    data = build_rows(global_res, china_res)

    counts = {}
    lines = [
        "-- 算法结果回灌 ADS 层（由 algorithm/hive_writer.py 自动生成）",
        f"-- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  分区 dt={dt}",
        "-- 用法：把本目录（5 个 CSV + 本脚本）整体拷到 Hive 节点，在该目录下执行：",
        "--   hive -f load_results.hql",
        "-- 注意：ADS 结果表按设计是 ORC + Snappy，而算法导出的是不带表头的 CSV；",
        "--   Hive 的 LOAD DATA 只搬文件不做格式转换，因此先 LOAD 到 TEXTFILE 临时表，",
        "--   再 INSERT ... SELECT 由 Hive 转成 ORC 写入目标分区。",
        f"USE {db};",
        "",
    ]
    for table, filename, columns in TABLE_SPECS:
        rows = data.get(table, [])
        counts[table] = len(rows)
        path = os.path.join(out_dir, filename)
        with open(path, "w", encoding="utf-8", newline="") as f:
            # 固定用 \n，避免 Windows 的 \r\n 在 Linux Hive 上把 \r 带进最后一列。
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore",
                                    lineterminator="\n")
            writer.writerows([{c: _safe(r.get(c, "")) for c in columns} for r in rows])
        types = TABLE_COLUMN_TYPES[table]
        assert len(types) == len(columns), f"{table} 列定义与 DDL 不一致"
        tmp = f"tmp_{table}"
        col_def = ",\n  ".join(f"{c} {t}" for c, t in zip(columns, types))
        col_sel = ", ".join(columns)
        lines += [
            f"-- {table}: {len(rows)} 行",
            f"DROP TABLE IF EXISTS {tmp};",
            f"CREATE TABLE {tmp} (",
            f"  {col_def}",
            ") ROW FORMAT DELIMITED FIELDS TERMINATED BY ',' STORED AS TEXTFILE;",
            f"LOAD DATA LOCAL INPATH '{filename}' OVERWRITE INTO TABLE {tmp};",
            f"INSERT OVERWRITE TABLE {table} PARTITION (dt='{dt}')",
            f"SELECT {col_sel} FROM {tmp};",
            f"DROP TABLE {tmp};",
            "",
        ]
    lines.append("-- 更新统计信息，便于 Spark SQL / Hive 优化执行计划")
    for table, _, _ in TABLE_SPECS:
        lines.append(f"ANALYZE TABLE {table} PARTITION (dt='{dt}') COMPUTE STATISTICS;")

    hql = os.path.join(out_dir, "load_results.hql")
    with open(hql, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return out_dir, hql, counts
