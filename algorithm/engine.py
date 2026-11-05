# -*- coding: utf-8 -*-
"""编排入口：加载 -> 构图 -> 全套指标 -> 导出。

运行方式（在含 algorithm/ 与 tests/ 的仓库根目录下执行）：
  1) 本地模式（默认，读项目根 data/raw 真实数据）：
       python -m algorithm.engine
  2) Hive 生产模式（待集群配置后启用）：
       在 config.HIVE_CONFIG 填真实连接，调用 loader.load_from_hive()
"""
import os

import networkx as nx
from . import config
from .loader import load_airports, load_routes, load_throughput, load_capacity
from .graph_builder import build_graph
from . import metrics
from .vulnerability import vulnerability_simulation
from .warning import saturation_warning, throughput_warning
from .regional import filter_region
from .report import (build_airport_rows, build_edge_rows, write_csv,
                     write_json, write_excel)

# 预警结果为空时仍写出表头，避免下游看板 / 成员C 读取时报「无表头」
SATURATION_WARNING_FIELDS = ("airport_id", "iata", "name", "utilization", "level")
THROUGHPUT_WARNING_FIELDS = ("airport_id", "iata", "name", "throughput_2023", "level")


def run_analysis(G, label="global", real_tp=None, real_cap=None):
    """对给定图 G 执行全部核心算法，返回结果字典并写出文件(前缀 label)。

    real_tp: 节点ID -> 2023真实年旅客吞吐量；real_cap: 节点ID -> 设计容量。
    两者皆备的机场方计算真实利用率并进入容量饱和预警。
    返回的 airport_rows 供汇总 Excel 复用，避免重复全量计算。
    """
    if G.number_of_nodes() == 0:
        raise ValueError("run_analysis: 图为空，无法计算指标；请检查区域关键词或数据源。")

    real_tp = real_tp or {}
    real_cap = real_cap or {}
    k = config.BETWEENNESS_SAMPLE_K if G.number_of_nodes() > 2000 else None
    centrality = metrics.compute_centrality(G, k=k)
    coupling, util = metrics.node_coupling(G, centrality, real_tp, real_cap)
    edge_coupling_map = metrics.edge_coupling(G, real_tp, real_cap)
    bottleneck_node = metrics.node_bottleneck(G, centrality, coupling, util)
    # 边介数（用于边瓶颈）
    Gu = G.to_undirected()
    edge_bt = nx.edge_betweenness_centrality(Gu, k=k, weight="weight", seed=42) if k \
        else nx.edge_betweenness_centrality(Gu, weight="weight")
    edge_bottleneck_map = metrics.edge_bottleneck(G, edge_coupling_map, edge_bt)

    warnings = saturation_warning(G, util)
    tp_warnings = throughput_warning(G, real_tp)
    vuln = vulnerability_simulation(G, centrality, score_key="betweenness")

    # 导出
    airport_rows = build_airport_rows(G, centrality, coupling, util, bottleneck_node,
                                     real_tp=real_tp, real_cap=real_cap)
    edge_rows = build_edge_rows(G, edge_bottleneck_map, edge_coupling_map)
    p_air = write_csv(airport_rows, f"{label}_airport_metrics.csv")
    p_edge = write_csv(edge_rows, f"{label}_edge_bottleneck.csv")
    p_warn = write_csv(
        [{"airport_id": w["node"], "iata": G.nodes[w["node"]].get("iata", ""),
          "name": G.nodes[w["node"]].get("name", ""),
          "utilization": round(w["utilization"], 6), "level": w["level"]} for w in warnings],
        f"{label}_saturation_warnings.csv", fieldnames=SATURATION_WARNING_FIELDS)
    p_tpw = write_csv(
        [{"airport_id": w["node"], "iata": w["iata"], "name": w["name"],
          "throughput_2023": w["throughput"], "level": w["level"]} for w in tp_warnings],
        f"{label}_throughput_warnings.csv", fieldnames=THROUGHPUT_WARNING_FIELDS)
    p_vuln = write_json(vuln, f"{label}_vulnerability.json")

    return {
        "label": label,
        "n_nodes": G.number_of_nodes(),
        "n_edges": G.number_of_edges(),
        "top_coupling": airport_rows[:10],
        "top_bottleneck_edges": edge_rows[:10],
        "n_warnings": len(warnings),
        "n_tp_warnings": len(tp_warnings),
        "vuln_base_lcc": vuln["base_lcc"],
        "vuln_by_k": vuln["by_k"],
        "airport_rows": airport_rows,
        "files": {"airport": p_air, "edge": p_edge, "warnings": p_warn,
                  "tp_warnings": p_tpw, "vuln": p_vuln},
    }


def main():
    missing = [p for p in config.REQUIRED_DATA_FILES if not os.path.isfile(p)]
    if missing:
        raise FileNotFoundError(
            "缺少原始数据文件：\n  " + "\n  ".join(missing) +
            "\n请确认 data/raw/ 数据包已放在项目根，或设置环境变量 "
            "CIVIL_AVIATION_PROJECT_ROOT 指向项目根目录。"
        )

    print(">> 加载原始数据（本地模式）...")
    airports = load_airports()
    routes = load_routes()
    print(f"   机场: {len(airports)}  航段记录: {len(routes)}")

    # 真实吞吐量（2023 年真实旅客吞吐量，按 IATA 接入）
    tp_iata = load_throughput() if config.USE_REAL_THROUGHPUT else {}
    tp_note = "（来源 airport_throughput_2023.csv）" if config.USE_REAL_THROUGHPUT \
        else "（真实数据开关已关闭）"
    print(f"   真实吞吐量记录: {len(tp_iata)} 条{tp_note}")

    # 真实设计容量（权威公开来源，按 IATA 接入）
    cap_iata = load_capacity() if config.USE_REAL_CAPACITY else {}
    cap_note = "（来源 airport_capacity_2023.csv）" if config.USE_REAL_CAPACITY \
        else "（真实数据开关已关闭）"
    print(f"   真实设计容量记录: {len(cap_iata)} 条{cap_note}")

    print(">> 构建航线网络有向加权图...")
    G, info = build_graph(airports, routes)
    print(f"   节点={info['nodes']} 边={info['edges']} "
          f"孤立航段={info['skipped_orphan_routes']} 自环={info['self_loops_removed']}")

    real_tp = metrics.build_real_throughput_map(G, tp_iata)
    real_cap = metrics.build_real_capacity_map(G, cap_iata)
    print(f"   成功对照真实吞吐量的图节点: {len(real_tp)} 个")
    print(f"   成功对照真实设计容量的图节点: {len(real_cap)} 个")

    print(">> 运行全局核心算法...")
    g_res = run_analysis(G, label="global", real_tp=real_tp, real_cap=real_cap)

    print(">> 运行中国区域子图核心算法（含港澳台）...")
    Gc = filter_region(G)
    if Gc.number_of_nodes() > 0:
        real_tp_c = metrics.build_real_throughput_map(Gc, tp_iata)
        real_cap_c = metrics.build_real_capacity_map(Gc, cap_iata)
        c_res = run_analysis(Gc, label="china", real_tp=real_tp_c, real_cap=real_cap_c)
        print(f"   中国子图: 节点={c_res['n_nodes']} 边={c_res['n_edges']} "
              f"容量预警={c_res['n_warnings']} 高吞吐量预警={c_res['n_tp_warnings']}")
    else:
        print("   警告：中国区域子图为空，请检查 REGION_KEYWORDS。")
        c_res = None

    # 汇总 Excel（多 sheet）：直接复用 run_analysis 的结果，不再重复全量计算
    sheets = [("global_airport_metrics", g_res["airport_rows"])]
    if c_res is not None:
        sheets.append(("china_airport_metrics", c_res["airport_rows"]))
    excel_path = write_excel(sheets, "civil_aviation_results.xlsx")

    # 控制台摘要
    print("\n================ 全局结果摘要 ================")
    print(f"节点/边: {g_res['n_nodes']}/{g_res['n_edges']}")
    print(f"容量饱和预警机场数: {g_res['n_warnings']}（基于真实设计容量，仅覆盖有容量数据的机场）")
    print(f"高吞吐量(繁忙度)预警机场数: {g_res['n_tp_warnings']}（基于2023真实旅客量，辅助参考）")
    print("Top5 耦合权重机场:")
    for r in g_res["top_coupling"][:5]:
        tpv = r.get("real_throughput_2023", "")
        tps = f" 真实吞吐={tpv:,}" if tpv != "" else ""
        capv = r.get("design_capacity", "")
        caps = f" 设计容量={capv:,}" if capv != "" else ""
        print(f"   {r['iata'] or r['airport_id']:>5} {r['name'][:24]:<24} "
              f"耦合={r['coupling']:.4f}{tps}{caps}")
    print("脆弱性(按介数移除 Top-K 后最大连通分量收缩):")
    for kk in g_res["vuln_by_k"]:
        print(f"   k={kk['k']:>2} 移除={kk['removed']:>2} LCC={kk['lcc']:>5} "
              f"下降={kk['lcc_drop_ratio']*100:5.1f}%")
    print(f"\n>> 结果文件已写入: {config.DATA_PROC_DIR}")
    print(f"   汇总 Excel: {excel_path}")
    return g_res, c_res


if __name__ == "__main__":
    main()
