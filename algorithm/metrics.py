# -*- coding: utf-8 -*-
"""核心指标：中心性、容量耦合权重、结构性瓶颈识别。"""
import networkx as nx
from .config import ALPHA, BETA, BETWEENNESS_SAMPLE_K


def _max_or_one(values):
    """取最大值；空序列或全零时返回 1.0，避免空图崩溃与归一化除零。"""
    return max(values, default=0) or 1.0


# ------------------------------------------------------------------ 中心性
def compute_centrality(G, k=BETWEENNESS_SAMPLE_K):
    """返回各中心性字典（键为节点）。

    k 为介数中心性抽样数；节点数不超过 k 时自动退化为精确计算，
    避免 networkx 在抽样数大于节点数时抛错（区域子图通常远小于 k）。
    """
    if k and G.number_of_nodes() <= k:
        k = None

    wdeg_out = dict(G.out_degree(weight="weight"))
    wdeg_in = dict(G.in_degree(weight="weight"))
    wdeg = {n: wdeg_out[n] + wdeg_in[n] for n in G}

    Gu = G.to_undirected()
    try:
        closeness = nx.closeness_centrality(Gu)
    except Exception:  # 异常权重/孤立点下降级为 0，保证流水线不中断
        closeness = {n: 0.0 for n in G}

    betweenness = (nx.betweenness_centrality(Gu, k=k, weight="weight", seed=42)
                   if k else nx.betweenness_centrality(Gu, weight="weight"))

    try:
        pagerank = nx.pagerank(G, weight="weight")
    except Exception:  # PowerIterationFailedConvergence 等下降级为 0
        pagerank = {n: 0.0 for n in G}

    return {
        "weighted_degree": wdeg,
        "weighted_out_degree": wdeg_out,
        "weighted_in_degree": wdeg_in,
        "closeness": closeness,
        "betweenness": betweenness,
        "pagerank": pagerank,
    }


# ------------------------------------------------------------------ 耦合权重
def compute_throughput_proxy(G, centrality):
    """吞吐量代理：用加权关联航段数（入+出）近似真实客流量。"""
    return {n: centrality["weighted_degree"][n] for n in G}


def _map_iata_values(G, value_iata_map):
    """把「IATA -> 数值」映射转换为「图节点 ID -> 数值」（仅保留能对上的节点）。"""
    if not value_iata_map:
        return {}
    return {n: value_iata_map[d.get("iata", "")]
            for n, d in G.nodes(data=True)
            if d.get("iata", "") in value_iata_map}


def build_real_throughput_map(G, throughput_iata_map):
    """真实年旅客吞吐量映射到图节点（供高吞吐量预警 / 利用率计算使用）。"""
    return _map_iata_values(G, throughput_iata_map)


def build_real_capacity_map(G, capacity_iata_map):
    """真实设计容量映射到图节点（供容量饱和预警计算利用率使用）。"""
    return _map_iata_values(G, capacity_iata_map)


def node_coupling(G, centrality, real_tp_map, capacity_map=None):
    """节点容量耦合权重 = ALPHA * 利用率 + BETA * 归一化中心性。

    利用率 u = 真实年旅客吞吐量 / 设计容量（仅当该机场同时具备真实吞吐与真实容量时计算）；
    缺容量数据的机场 u=0，不参与容量饱和预警，但中心性项仍计入耦合权重。
    """
    real_tp_map = real_tp_map or {}
    capacity_map = capacity_map or {}
    maxc = _max_or_one(centrality["weighted_degree"].values())
    coupling, util = {}, {}
    for n in G:
        tp = real_tp_map.get(n, 0) or 0
        cap = capacity_map.get(n) or 0
        u = (tp / cap) if (cap > 0 and tp > 0) else 0.0
        cen = centrality["weighted_degree"][n] / maxc
        util[n] = u
        coupling[n] = ALPHA * u + BETA * cen
    return coupling, util


def edge_coupling(G, real_tp_map, capacity_map=None):
    """边容量耦合权重 = ALPHA*平均利用率(端点) + BETA*吞吐占容量比(端点)。

    利用率 u = 真实吞吐 / 设计容量（端点缺容量时按 0 处理）；
    avg_tp 为两端点真实吞吐之和占其设计容量之和的比例。
    """
    real_tp_map = real_tp_map or {}
    capacity_map = capacity_map or {}
    ec = {}
    for s, d in G.edges():
        tps, tpd = real_tp_map.get(s, 0) or 0, real_tp_map.get(d, 0) or 0
        cs, cd = capacity_map.get(s) or 0, capacity_map.get(d) or 0
        us = (tps / cs) if (cs > 0 and tps > 0) else 0.0
        ud = (tpd / cd) if (cd > 0 and tpd > 0) else 0.0
        avg_u = 0.5 * us + 0.5 * ud
        avg_tp = (tps + tpd) / (cs + cd) if (cs > 0 and cd > 0) else 0.0
        ec[(s, d)] = ALPHA * avg_u + BETA * avg_tp
    return ec


# ------------------------------------------------------------------ 瓶颈识别
def node_bottleneck(G, centrality, coupling, util):
    """节点瓶颈分 = 归一化介数 * (0.5*利用率 + 0.5*耦合)。"""
    maxbt = _max_or_one(centrality["betweenness"].values())
    score = {}
    for n in G:
        nb = centrality["betweenness"][n] / maxbt
        score[n] = nb * (0.5 * util[n] + 0.5 * coupling[n])
    return score


def edge_bottleneck(G, edge_coupling_map, edge_betweenness=None):
    """航段瓶颈分 = 归一化边介数 * 边耦合权重。

    若 edge_betweenness 为空/None（缺介数信息），降级为按边耦合权重单独评分；
    全零边介数时用 1.0 作分母，避免 ZeroDivisionError。
    """
    has_eb = bool(edge_betweenness)
    maxeb = _max_or_one(edge_betweenness.values()) if has_eb else 1.0
    score = {}
    for (s, d) in G.edges():
        coupling = edge_coupling_map.get((s, d), 0.0)
        score[(s, d)] = (edge_betweenness.get((s, d), 0.0) / maxeb) * coupling \
            if has_eb else coupling
    return score
