# -*- coding: utf-8 -*-
"""区域子图筛选：按国家/地区字段关键词（默认含中国及港澳台）。"""
from .config import REGION_KEYWORDS, REGION_KEYWORDS_CN


def filter_region(G, keywords=REGION_KEYWORDS):
    """返回仅含指定国家/地区机场的子图（深拷贝，保持图结构与属性）。

    默认关键词下：
      - 英文国家名按 country 字段**精确相等**匹配，避免把美国 "China Lake"、
        巴基斯坦 "Parachinar" 这类含 china 子串的地名误纳入中国子图；
      - 另兼容 Hive ADS 层可能只提供中文 province / city 的情况，
        用中文别名（默认关键词下自动生效）在这三个字段中做子串匹配。
    传入自定义 keywords 时严格沿用原有「子串匹配 country」行为，便于外部按需筛选。
    """
    if keywords is REGION_KEYWORDS:
        en = {k.lower() for k in REGION_KEYWORDS}
        cn = tuple(k.lower() for k in REGION_KEYWORDS_CN)

        def hit(d):
            country = str(d.get("country") or "").strip().lower()
            if country in en:
                return True
            text = " ".join(str(d.get(f) or "")
                            for f in ("country", "province", "city")).lower()
            return any(k in text for k in cn)
    else:
        kws = [k.lower() for k in keywords]

        def hit(d):
            country = str(d.get("country") or "").lower()
            return any(k in country for k in kws)

    nodes = [n for n, d in G.nodes(data=True) if hit(d)]
    return G.subgraph(nodes).copy()
