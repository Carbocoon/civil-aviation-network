# -*- coding: utf-8 -*-
"""预警：容量饱和预警（主功能）与高吞吐量预警（辅助参考）。"""
from .config import TAU1, TAU2, HIGH_TP_LEVEL1, HIGH_TP_LEVEL2


def saturation_warning(G, util):
    """容量饱和预警：基于真实利用率 u = 真实吞吐量 / 真实设计容量。

    level: 2=接近饱和/严重(>=tau2), 1=偏繁忙(>=tau1)；按利用率降序返回。
    无真实容量数据的机场 util=0，自动不计入预警（不编造占位值）。
    """
    util = util or {}
    warnings = []
    for n in G:
        u = util.get(n, 0.0) or 0.0
        if not isinstance(u, (int, float)) or u < TAU1:
            continue
        warnings.append({"node": n, "utilization": u,
                         "level": 2 if u >= TAU2 else 1})
    warnings.sort(key=lambda x: x["utilization"], reverse=True)
    return warnings


def throughput_warning(G, throughput_map, lvl1=HIGH_TP_LEVEL1, lvl2=HIGH_TP_LEVEL2):
    """高吞吐量(繁忙度)预警：直接用真实年旅客吞吐量判级，仅作辅助参考。

    level: 2=高度繁忙(>=lvl2), 1=繁忙(>=lvl1)；返回按吞吐量降序的列表。
    容量饱和判定请以 saturation_warning() 为准，本函数不衡量"接近设计上限"。
    """
    if not throughput_map:
        return []
    warnings = []
    for n, tp in throughput_map.items():
        if n not in G or not isinstance(tp, (int, float)) or tp < lvl1:
            continue
        warnings.append({
            "node": n,
            "iata": G.nodes[n].get("iata", ""),
            "name": G.nodes[n].get("name", ""),
            "throughput": tp,
            "level": 2 if tp >= lvl2 else 1,
        })
    warnings.sort(key=lambda x: x["throughput"], reverse=True)
    return warnings
