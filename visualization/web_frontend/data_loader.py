# -*- coding: utf-8 -*-
"""读取算法产出的 data/processed 结果文件，供 Streamlit 看板消费。

约定（对应分工文档 13.3）：
- 路径不写死本机绝对路径：优先取环境变量 CIVIL_AVIATION_PROJECT_ROOT，
  否则从本文件向上逐级查找含 data/processed 的目录；切到 Hive 只改数据来源，
  结果目录不变。
- 任何文件缺失 / 结果为空都返回「带标准表头」的空 DataFrame，看板不会因缺列崩溃。
- 容量饱和预警（saturation）是正式功能；高吞吐量预警（throughput）仅辅助参考。

结果文件（data/processed/，前缀 label = global / china）：
  {label}_airport_metrics.csv     机场指标汇总
  {label}_edge_bottleneck.csv     航段瓶颈
  {label}_saturation_warnings.csv 容量饱和预警（主功能）
  {label}_throughput_warnings.csv 高吞吐量繁忙度预警（辅助参考）
  {label}_vulnerability.json      脆弱性仿真结果
  civil_aviation_results.xlsx     汇总（两个 sheet）
"""
import csv
import json
import os

import pandas as pd

VALID_LABELS = ("global", "china")

# 列定义与 algorithm/report.py 严格对齐
AIRPORT_COLUMNS = [
    "airport_id", "iata", "name", "city", "country",
    "w_degree", "w_out", "w_in", "closeness", "betweenness", "pagerank",
    "design_capacity", "real_throughput_2023", "utilization", "coupling", "bottleneck",
]
# 经纬度只用于拓扑图摆点，不属于算法结果列契约，不写入 data/processed。
COORD_COLUMNS = ["airport_id", "iata", "lat", "lng"]
EDGE_COLUMNS = ["src_id", "dst_id", "weight", "edge_coupling", "bottleneck"]
SATURATION_COLUMNS = ["airport_id", "iata", "name", "utilization", "level"]
THROUGHPUT_COLUMNS = ["airport_id", "iata", "name", "throughput_2023", "level"]
SUBSCRIPTION_COLUMNS = ["email", "level", "region", "created_at"]


def _project_root() -> str:
    """定位项目根（含 data/processed 的目录）。"""
    override = os.environ.get("CIVIL_AVIATION_PROJECT_ROOT")
    if override and os.path.isdir(os.path.join(override, "data", "processed")):
        return os.path.abspath(override)
    cur = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        if os.path.isdir(os.path.join(cur, "data", "processed")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))


ROOT = _project_root()
PROC_DIR = os.path.join(ROOT, "data", "processed")
SUBSCRIPTION_FILE = os.path.join(ROOT, "subscriptions.csv")


def _proc_path(filename: str) -> str:
    return os.path.join(PROC_DIR, filename)


def _ensure_columns(df: pd.DataFrame, columns) -> pd.DataFrame:
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df


def _read_csv_safe(filename: str, columns=None):
    """读 CSV；缺失/损坏一律返回带标准表头的空表，看板不报错。"""
    path = _proc_path(filename)
    if not os.path.isfile(path):
        return pd.DataFrame(columns=list(columns or [])), path
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", on_bad_lines="skip")
    except Exception:
        return pd.DataFrame(columns=list(columns or [])), path
    return _ensure_columns(df, columns or []), path


def _normalize_label(label: str) -> str:
    return label if label in VALID_LABELS else "global"


def load_airport_metrics(label: str = "global"):
    label = _normalize_label(label)
    return _read_csv_safe(f"{label}_airport_metrics.csv", AIRPORT_COLUMNS)


def load_edge_bottleneck(label: str = "global"):
    label = _normalize_label(label)
    return _read_csv_safe(f"{label}_edge_bottleneck.csv", EDGE_COLUMNS)


def load_saturation_warnings(label: str = "global"):
    """容量饱和预警（主功能）。"""
    label = _normalize_label(label)
    return _read_csv_safe(f"{label}_saturation_warnings.csv", SATURATION_COLUMNS)


def load_throughput_warnings(label: str = "global"):
    """高吞吐量繁忙度预警（辅助参考，非饱和度）。"""
    label = _normalize_label(label)
    return _read_csv_safe(f"{label}_throughput_warnings.csv", THROUGHPUT_COLUMNS)


def load_vulnerability(label: str = "global"):
    label = _normalize_label(label)
    path = _proc_path(f"{label}_vulnerability.json")
    if not os.path.isfile(path):
        return None, path
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), path
    except Exception as exc:
        return {"error": str(exc)}, path


def load_edges_with_iata(label: str = "global"):
    """航段表补上起降机场 IATA 三字码，供「容量流量下钻 / 反向查询」使用。

    本地结果里的 src_id/dst_id 是 OpenFlights 数字 ID；Hive 模式下本身即 IATA，
    两种情况都能正确映射（映射不到时保留原值）。
    """
    edges, _ = load_edge_bottleneck(label)
    airports, _ = load_airport_metrics(label)
    if edges.empty:
        return _ensure_columns(edges, EDGE_COLUMNS + ["src_iata", "dst_iata", "route"])
    id2iata = {}
    if not airports.empty:
        id2iata = {str(r["airport_id"]): (r.get("iata") or str(r["airport_id"]))
                   for _, r in airports.iterrows()}
    edges = edges.copy()
    edges["src_iata"] = edges["src_id"].astype(str).map(id2iata).fillna(
        edges["src_id"].astype(str))
    edges["dst_iata"] = edges["dst_id"].astype(str).map(id2iata).fillna(
        edges["dst_id"].astype(str))
    edges["route"] = edges["src_iata"] + " → " + edges["dst_iata"]
    return edges


def load_airport_coordinates() -> pd.DataFrame:
    """读取 data/raw/airports.dat 里的真实经纬度，仅用于网络拓扑图摆点。

    OpenFlights 的 airports.dat 是无表头 CSV，前 8 列为：
    id, name, city, country, IATA, ICAO, lat, lng, ...
    坐标是展示辅助信息，不是算法结果：结果文件 / Hive ADS 结果表都不需要加列，
    数据列契约（AIRPORT_COLUMNS）保持不变。
    文件缺失、格式异常或没有有效坐标时返回空表，拓扑图自动回退到力导向布局。
    """
    path = os.path.join(ROOT, "data", "raw", "airports.dat")
    rows = []
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        parts = next(csv.reader([line]))
                    except (csv.Error, StopIteration):
                        continue
                    if len(parts) < 8:
                        continue
                    lat = pd.to_numeric(parts[6], errors="coerce")
                    lng = pd.to_numeric(parts[7], errors="coerce")
                    if pd.isna(lat) or pd.isna(lng):
                        continue
                    iata = parts[4].strip()
                    rows.append({
                        "airport_id": parts[0].strip(),
                        "iata": "" if iata in ("", "\\N", "N/A") else iata,
                        "lat": float(lat), "lng": float(lng),
                    })
        except OSError:
            pass
    return pd.DataFrame(rows, columns=COORD_COLUMNS)


def attach_coordinates(airport_df: pd.DataFrame, coords=None) -> pd.DataFrame:
    """给机场指标表补 lat / lng 两列（不会改动调用方的原表）。

    本地结果表的 airport_id 是 OpenFlights 数字 ID；Hive 模式下就是 IATA，
    因此先按 airport_id 匹配、匹配不到再按 IATA 兜底。匹配不到的留 NaN，
    charts.geo_layout 会给它们安排确定性的外围位置，不会全挤在中心。
    """
    df = airport_df.copy()
    df["lat"] = float("nan")
    df["lng"] = float("nan")
    if coords is None:
        coords = load_airport_coordinates()
    if df.empty or coords is None or coords.empty:
        return df
    c = coords.copy()
    c["_id"] = c["airport_id"].astype(str)
    c["_iata"] = c["iata"].astype(str).str.strip().str.upper()
    by_id = c.drop_duplicates("_id").set_index("_id")
    by_iata = c[c["_iata"] != ""].drop_duplicates("_iata").set_index("_iata")
    ids = df["airport_id"].astype(str)
    iatas = df["iata"].astype(str).str.strip().str.upper()
    for col in ("lat", "lng"):
        df[col] = ids.map(by_id[col]).fillna(iatas.map(by_iata[col]))
    return df


def load_subscriptions() -> pd.DataFrame:
    if not os.path.isfile(SUBSCRIPTION_FILE):
        return pd.DataFrame(columns=SUBSCRIPTION_COLUMNS)
    try:
        df = pd.read_csv(SUBSCRIPTION_FILE, encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame(columns=SUBSCRIPTION_COLUMNS)
    return _ensure_columns(df, SUBSCRIPTION_COLUMNS)


def save_subscriptions(df: pd.DataFrame):
    df.to_csv(SUBSCRIPTION_FILE, index=False, encoding="utf-8-sig")


def data_dir_exists() -> bool:
    return os.path.isdir(PROC_DIR)
