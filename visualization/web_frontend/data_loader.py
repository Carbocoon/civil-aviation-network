# -*- coding: utf-8 -*-
"""读取算法产出的 data/processed 结果文件，供可视化层消费。

设计约定（对应分工文档 13.3）：
- 路径不写死本机绝对路径：优先取环境变量 CIVIL_AVIATION_PROJECT_ROOT，
  否则从本文件向上逐级查找含 data/processed 的目录；后续切到 Hive 只改数据源，
  输出目录不变。
- 文件缺失 / 结果为空时返回空 DataFrame（保留列由算法侧保证表头），看板不报错。
- 容量饱和预警（saturation）是正式功能；高吞吐量预警（throughput）仅辅助参考，
  展示层不得把它当作饱和度结论。

算法结果文件（data/processed/，前缀 label = global / china）：
  {label}_airport_metrics.csv     机场指标汇总（中心性/耦合/利用率/瓶颈）
  {label}_edge_bottleneck.csv     航段瓶颈
  {label}_saturation_warnings.csv 容量饱和预警（主功能）
  {label}_throughput_warnings.csv 高吞吐量繁忙度预警（辅助参考）
  {label}_vulnerability.json      脆弱性仿真结果
  civil_aviation_results.xlsx     汇总（两个 sheet）
"""
import os
import json
import pandas as pd

VALID_LABELS = ("global", "china")

# airport_metrics 表的标准列（与 algorithm/report.py: build_airport_rows 对齐）
AIRPORT_COLUMNS = [
    "airport_id", "iata", "name", "city", "country",
    "w_degree", "w_out", "w_in", "closeness", "betweenness", "pagerank",
    "design_capacity", "real_throughput_2023", "utilization", "coupling", "bottleneck",
]


def _project_root() -> str:
    """定位项目根（含 data/processed 的目录）。"""
    override = os.environ.get("CIVIL_AVIATION_PROJECT_ROOT")
    if override and os.path.isdir(os.path.join(override, "data", "processed")):
        return override
    cur = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        if os.path.isdir(os.path.join(cur, "data", "processed")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    # 回退：web_frontend 的上两级即仓库根
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


ROOT = _project_root()
PROC_DIR = os.path.join(ROOT, "data", "processed")


def _proc_path(filename: str) -> str:
    return os.path.join(PROC_DIR, filename)


def _read_csv_safe(filename: str):
    """读 CSV；文件不存在返回 (空DataFrame, 路径)。编码 utf-8-sig 兼容带 BOM。"""
    path = _proc_path(filename)
    if not os.path.isfile(path):
        return pd.DataFrame(), path
    try:
        return pd.read_csv(path, encoding="utf-8-sig"), path
    except Exception as exc:  # 脏数据兜底，避免看板崩溃
        return pd.DataFrame({"error": [str(exc)]}), path


def _normalize_label(label: str) -> str:
    return label if label in VALID_LABELS else "global"


def load_airport_metrics(label: str = "global"):
    """机场指标汇总表。返回 (DataFrame, 文件路径)。"""
    label = _normalize_label(label)
    df, path = _read_csv_safe(f"{label}_airport_metrics.csv")
    if not df.empty:
        for col in AIRPORT_COLUMNS:
            if col not in df.columns:
                df[col] = ""
    return df, path


def load_edge_bottleneck(label: str = "global"):
    """航段瓶颈表。返回 (DataFrame, 文件路径)。"""
    label = _normalize_label(label)
    return _read_csv_safe(f"{label}_edge_bottleneck.csv")


def load_saturation_warnings(label: str = "global"):
    """容量饱和预警（主功能）。返回 (DataFrame, 文件路径)。"""
    label = _normalize_label(label)
    return _read_csv_safe(f"{label}_saturation_warnings.csv")


def load_throughput_warnings(label: str = "global"):
    """高吞吐量繁忙度预警（辅助参考，非饱和度）。返回 (DataFrame, 文件路径)。"""
    label = _normalize_label(label)
    return _read_csv_safe(f"{label}_throughput_warnings.csv")


def load_vulnerability(label: str = "global"):
    """脆弱性仿真 JSON。返回 (dict, 文件路径)；缺失返回 (None, 路径)。"""
    label = _normalize_label(label)
    path = _proc_path(f"{label}_vulnerability.json")
    if not os.path.isfile(path):
        return None, path
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), path
    except Exception as exc:
        return {"error": str(exc)}, path


def data_dir_exists() -> bool:
    return os.path.isdir(PROC_DIR)
