# -*- coding: utf-8 -*-
"""构建航线网络有向加权图：机场=节点，航段=边，权重=航段频次。"""
import networkx as nx
from .loader import load_airports, load_routes


def build_graph(airports=None, routes=None, direct_only=True):
    """构建 DiGraph。

    Args:
        airports: load_airports() 的结果；None 时从本地文件加载（允许显式传空字典）。
        routes:   load_routes() 的结果；None 时从本地文件加载。
        direct_only: 仅保留直飞航段(stops==0)。
    Returns:
        G: nx.DiGraph（节点带 name/country/iata 等属性，边带 weight=频次）
        info: 构建统计（孤立航段数、自环数、节点数、边数）
    """
    if airports is None:
        airports = load_airports()
    if routes is None:
        routes = load_routes()

    G = nx.DiGraph()
    for aid, a in airports.items():
        G.add_node(aid, **a)

    edge_w = {}
    skipped_orphan = 0
    self_loops = 0
    for route in routes:
        if len(route) < 5:
            continue
        src, dst, _cs, stops, _eq = route[:5]
        if src not in G or dst not in G:
            skipped_orphan += 1
            continue
        if src == dst:
            self_loops += 1
            continue
        if direct_only and stops != 0:
            continue
        key = (src, dst)
        edge_w[key] = edge_w.get(key, 0) + 1

    for (s, d), w in edge_w.items():
        G.add_edge(s, d, weight=w)

    info = {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "skipped_orphan_routes": skipped_orphan,
        "self_loops_removed": self_loops,
    }
    return G, info
