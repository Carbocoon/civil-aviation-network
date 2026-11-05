# -*- coding: utf-8 -*-
"""结果导出：CSV / Excel / JSON。统一写入项目根 data/processed/。"""
import csv
import json
import os
from .config import DATA_PROC_DIR


def _ensure():
    os.makedirs(DATA_PROC_DIR, exist_ok=True)


def build_airport_rows(G, centrality, coupling, util, bottleneck_node, real_tp=None, real_cap=None):
    """将各机场指标合并为统一行表（按耦合权重降序）。"""
    real_tp = real_tp or {}
    real_cap = real_cap or {}
    rows = []
    for n in G:
        d = G.nodes[n]
        rows.append({
            "airport_id": n,
            "iata": d.get("iata", ""),
            "name": d.get("name", ""),
            "city": d.get("city", ""),
            "country": d.get("country", ""),
            "w_degree": round(centrality["weighted_degree"][n], 3),
            "w_out": round(centrality["weighted_out_degree"][n], 3),
            "w_in": round(centrality["weighted_in_degree"][n], 3),
            "closeness": round(centrality["closeness"][n], 6),
            "betweenness": round(centrality["betweenness"][n], 6),
            "pagerank": round(centrality["pagerank"][n], 8),
            "design_capacity": real_cap.get(n, ""),
            "real_throughput_2023": real_tp.get(n, ""),
            "utilization": round(util[n], 6),
            "coupling": round(coupling[n], 6),
            "bottleneck": round(bottleneck_node[n], 6),
        })
    rows.sort(key=lambda r: r["coupling"], reverse=True)
    return rows


def build_edge_rows(G, edge_bottleneck_map, edge_coupling_map):
    """航段(边)指标行表（按瓶颈分降序）。"""
    rows = []
    for (s, d) in G.edges():
        rows.append({
            "src_id": s,
            "dst_id": d,
            "weight": G[s][d].get("weight", 1),
            "edge_coupling": round(edge_coupling_map.get((s, d), 0.0), 6),
            "bottleneck": round(edge_bottleneck_map.get((s, d), 0.0), 6),
        })
    rows.sort(key=lambda r: r["bottleneck"], reverse=True)
    return rows


def write_csv(rows, filename, fieldnames=None):
    """写 CSV；rows 为空时若提供 fieldnames 仍写出表头，便于下游看板读取。"""
    _ensure()
    path = os.path.join(DATA_PROC_DIR, filename)
    header = list(fieldnames) if fieldnames else (list(rows[0].keys()) if rows else [])
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=header)
        if header:
            w.writeheader()
        if rows:
            w.writerows(rows)
    return path


def write_json(obj, filename):
    _ensure()
    path = os.path.join(DATA_PROC_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path


def write_excel(sheets, filename="results.xlsx"):
    """sheets: list[(sheet_name, rows)] 或 [(sheet_name, rows, fieldnames)]。

    三元组形式用于 rows 可能为空时仍保留表头；按表头顺序取值，
    避免字典键顺序变化导致列错位。
    """
    _ensure()
    from openpyxl import Workbook
    path = os.path.join(DATA_PROC_DIR, filename)
    wb = Workbook()
    first = True
    for item in sheets:
        name, rows = item[0], item[1]
        fieldnames = item[2] if len(item) > 2 else None
        ws = wb.active if first else wb.create_sheet(name)
        first = False
        ws.title = name[:31]
        header = list(fieldnames) if fieldnames else (list(rows[0].keys()) if rows else [])
        if header:
            ws.append(header)
        for r in rows:
            ws.append([r.get(h, "") for h in header])
    wb.save(path)
    return path
