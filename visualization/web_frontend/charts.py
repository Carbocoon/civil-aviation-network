# -*- coding: utf-8 -*-
"""图表构建：力导向网络布局 + Altair 图表。

只用自带的 numpy / pandas / altair，无需 plotly、networkx。
图表背景透明、文字与网格使用中性色，因此在浅色与深色主题下都能读。
"""
import numpy as np
import pandas as pd
import altair as alt

from ui import BRAND, AMBER, INK, GRID, EDGE

# Altair 图表统一用透明背景，交给页面主题决定底色
_BG = {"background": "transparent"}


def _numeric(series):
    """把可能是字符串/空的列安全转成数值，NaN 填 0。"""
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def _norm(series):
    """归一化到 [0,1]，全相等时返回 0.5，避免除零。"""
    v = _numeric(series).astype(float)
    lo, hi = float(v.min()), float(v.max())
    if hi - lo < 1e-12:
        return pd.Series([0.5] * len(v), index=v.index)
    return (v - lo) / (hi - lo)


def spring_layout(node_ids, edges, seed=42, iterations=90):
    """简化 Fruchterman-Reingold 力导向布局（O(n²)·iter，Top 200 节点足够快）。"""
    ids = list(node_ids)
    n = len(ids)
    if n == 0:
        return {}
    rng = np.random.default_rng(seed)
    pos = rng.uniform(-1.0, 1.0, size=(n, 2))
    index = {nid: i for i, nid in enumerate(ids)}
    pairs = np.array([[index[s], index[d]] for s, d in edges
                      if s in index and d in index and s != d], dtype=int)
    k = np.sqrt(1.0 / max(n, 1))
    temp = 0.55
    for _ in range(iterations):
        delta = pos[:, None, :] - pos[None, :, :]          # (n,n,2)
        dist = np.sqrt((delta ** 2).sum(-1)) + 1e-6
        np.fill_diagonal(dist, np.inf)
        repulsion = (delta / dist[:, :, None] ** 2) * (k ** 2)
        force = repulsion.sum(axis=1)
        if len(pairs):
            d = pos[pairs[:, 0]] - pos[pairs[:, 1]]
            length = np.sqrt((d ** 2).sum(1)) + 1e-6
            attraction = (d / length[:, None]) * (length[:, None] ** 2 / k)
            np.add.at(force, pairs[:, 0], -attraction)
            np.add.at(force, pairs[:, 1], attraction)
        flen = np.linalg.norm(force, axis=1, keepdims=True) + 1e-9
        pos += force / flen * np.minimum(flen, temp)
        temp *= 0.972
    lo, hi = pos.min(axis=0), pos.max(axis=0)
    span = np.where(hi - lo < 1e-9, 1.0, hi - lo)
    pos = (pos - lo) / span
    return {nid: (float(pos[i, 0]), float(pos[i, 1])) for i, nid in enumerate(ids)}


def geo_layout(node_ids, lat, lng, seed=42):
    """用真实经纬度摆点（等距圆柱投影 + 按当前显示点自适应缩放）。

    力导向布局会把彼此相连的大枢纽全部拉到画布中心，航线网络恰好是
    「少数枢纽连成一片」的结构，因此中间必然堆成一团。这里改成按机场的
    实际地理位置摆放：既散得开，位置本身也有含义（中国子图会自动放大到
    整张画布，不会被全球范围压成一小块）。

    - 经度按数据中心展开，避免跨国际日期变更线的航线画成贯穿全图的长横线；
    - 用 2%~98% 分位数裁剪极端孤立点，防止一两个偏远机场把其余点压缩；
    - 无坐标的点放到画布外围的确定性位置，不挤在中心，也不伪装成真实坐标。
    """
    ids = list(node_ids)
    if not ids:
        return {}
    la = np.asarray(pd.to_numeric(pd.Series(lat), errors="coerce"), dtype=float)
    lo = np.asarray(pd.to_numeric(pd.Series(lng), errors="coerce"), dtype=float)
    if len(la) != len(ids):
        la = np.resize(la, len(ids))
    if len(lo) != len(ids):
        lo = np.resize(lo, len(ids))
    valid = (np.isfinite(la) & np.isfinite(lo)
             & (np.abs(la) <= 90) & (np.abs(lo) <= 180))

    x = lo.astype(float).copy()
    center = float(np.median(x[valid])) if valid.any() else 0.0
    x = np.where(x - center > 180, x - 360,
                 np.where(x - center < -180, x + 360, x))
    y = la.astype(float).copy()
    if valid.sum() >= 2:
        xlo, xhi = np.percentile(x[valid], [2, 98])
        ylo, yhi = np.percentile(y[valid], [2, 98])
        if xhi - xlo < 1e-9:
            xlo, xhi = xlo - 1.0, xhi + 1.0
        if yhi - ylo < 1e-9:
            ylo, yhi = ylo - 1.0, yhi + 1.0
        px = 0.04 + 0.92 * (x - xlo) / (xhi - xlo)
        py = 0.96 - 0.92 * (y - ylo) / (yhi - ylo)   # 纬度高在上
    else:
        px = np.full(len(ids), 0.5)
        py = np.full(len(ids), 0.5)

    rng = np.random.default_rng(seed)
    if (~valid).any():
        angle = rng.uniform(0, 2 * np.pi, int((~valid).sum()))
        radius = rng.uniform(0.42, 0.49, int((~valid).sum()))
        px[~valid] = 0.5 + radius * np.cos(angle)
        py[~valid] = 0.5 + radius * np.sin(angle) * 0.9
    px = np.clip(px, 0.0, 1.0)
    py = np.clip(py, 0.0, 1.0)
    return {nid: (float(px[i]), float(py[i])) for i, nid in enumerate(ids)}


TOOLTIPS = [
    alt.Tooltip("iata:N", title="三字码"),
    alt.Tooltip("name:N", title="机场"),
    alt.Tooltip("city:N", title="城市"),
    alt.Tooltip("country:N", title="国家"),
    alt.Tooltip("coupling:Q", title="耦合权重", format=".4f"),
    alt.Tooltip("utilization:Q", title="容量利用率", format=".4f"),
    alt.Tooltip("real_throughput_2023:Q", title="2023 吞吐量", format=",.0f"),
    alt.Tooltip("design_capacity:Q", title="设计容量", format=",.0f"),
    alt.Tooltip("w_degree:Q", title="加权度", format=",.0f"),
    alt.Tooltip("betweenness:Q", title="介数中心性", format=".5f"),
    alt.Tooltip("pagerank:Q", title="PageRank", format=".6f"),
]


def network_chart(nodes_df, edges_df, size_col="coupling", color_col="utilization",
                  focus_id=None, label_top=5, height=560, layout="auto",
                  max_edges=150, seed=42):
    """返回 (altair 图层, 节点位置表)；位置表里带 `_layout` 标明实际用的布局。

    layout: "auto" 有足够真实经纬度就用 geo_layout，否则回退 spring_layout；
            "geo" 强制地理布局；"spring" 强制力导向布局。
    节点大小/颜色可按指标切换；边宽映射航段权重、最多画 max_edges 条；
    focus_id 的机场加橙环并高亮相邻航段（其余连线压淡，避免中心糊成一团）。
    """
    nodes = nodes_df.copy().reset_index(drop=True)
    if nodes.empty:
        return None, pd.DataFrame()
    for c in ("coupling", "utilization", "real_throughput_2023", "design_capacity",
              "w_degree", "betweenness", "pagerank", size_col, color_col):
        if c in nodes.columns:
            nodes[c] = _numeric(nodes[c])
        else:
            nodes[c] = 0.0
    for c in ("iata", "name", "city", "country"):
        if c not in nodes.columns:
            nodes[c] = ""
    # 圆点上限从 900 降到 400，大枢纽不再互相盖住
    nodes["_size"] = 40 + 360 * _norm(nodes[size_col])
    nodes["_color"] = _numeric(nodes[color_col])

    ids = nodes["airport_id"].tolist()
    has_coord = ("lat" in nodes.columns and "lng" in nodes.columns)
    if has_coord:
        la = pd.to_numeric(nodes["lat"], errors="coerce")
        lo = pd.to_numeric(nodes["lng"], errors="coerce")
        coverage = float((la.notna() & lo.notna()).mean())
    else:
        coverage = 0.0
    use_geo = (layout == "geo" or
               (layout == "auto" and has_coord and coverage >= 0.6))
    nodes["_layout"] = "geo" if use_geo else "spring"

    # 只画两端都在当前显示集合内、且排在最前的若干条航段
    valid_ids = set(ids)
    e = pd.DataFrame()
    if edges_df is not None and not edges_df.empty:
        e = edges_df.copy()
        for c in ("weight", "bottleneck"):
            e[c] = _numeric(e.get(c, pd.Series([1] * len(e))))
        e = e[e["src_id"].isin(valid_ids) & e["dst_id"].isin(valid_ids)]
        if max_edges:
            e = e.head(int(max_edges))
    edge_pairs = list(zip(e["src_id"], e["dst_id"])) if not e.empty else []

    if use_geo:
        pos = geo_layout(ids, nodes["lat"], nodes["lng"], seed=seed)
    else:
        pos = spring_layout(ids, edge_pairs, seed=seed)
    nodes["x"] = nodes["airport_id"].map(lambda i: pos.get(i, (0.5, 0.5))[0])
    nodes["y"] = nodes["airport_id"].map(lambda i: pos.get(i, (0.5, 0.5))[1])

    layers = []
    if edge_pairs:
        e = e.reset_index(drop=True)
        e["_id"] = np.arange(len(e)).astype(str)
        e["x"] = e["src_id"].map(lambda i: pos.get(i, (0.5, 0.5))[0])
        e["y"] = e["src_id"].map(lambda i: pos.get(i, (0.5, 0.5))[1])
        e["x2"] = e["dst_id"].map(lambda i: pos.get(i, (0.5, 0.5))[0])
        e["y2"] = e["dst_id"].map(lambda i: pos.get(i, (0.5, 0.5))[1])
        e["_w"] = 0.5 + 2.5 * _norm(e["weight"])
        if focus_id is not None:
            e["_hl"] = np.where((e["src_id"] == focus_id) | (e["dst_id"] == focus_id),
                                "关联航段", "其他航段")
            e = e.sort_values("_hl")  # 高亮线后画，避免被覆盖
        else:
            e["_hl"] = "航段"
        e["_op"] = np.where(e["_hl"] == "关联航段", 0.88, 0.28)
        line = alt.Chart(e).mark_line().encode(
            x=alt.X("x:Q", axis=None), y=alt.Y("y:Q", axis=None),
            x2="x2:Q", y2="y2:Q", detail="_id:N",
            size=alt.Size("_w:Q", scale=alt.Scale(range=[0.5, 3.0]), legend=None),
            opacity=alt.Opacity("_op:Q", scale=None, legend=None),
            color=alt.Color("_hl:N",
                            scale=alt.Scale(domain=["关联航段", "其他航段", "航段"],
                                            range=[AMBER, EDGE, EDGE]),
                            legend=alt.Legend(title="连线", orient="bottom")),
        )
        layers.append(line)

    color_scale = alt.Scale(scheme="orangered" if color_col == "utilization"
                            else "teals")
    points = alt.Chart(nodes).mark_circle(opacity=0.92, stroke=EDGE,
                                          strokeWidth=1.0).encode(
        x=alt.X("x:Q", axis=None, scale=alt.Scale(domain=[-0.06, 1.06])),
        y=alt.Y("y:Q", axis=None, scale=alt.Scale(domain=[-0.06, 1.06])),
        size=alt.Size("_size:Q", scale=None, legend=None),
        color=alt.Color("_color:Q", scale=color_scale,
                        legend=alt.Legend(title=color_col, orient="bottom",
                                          gradientLength=220)),
        tooltip=TOOLTIPS,
    )
    layers.append(points)

    # 标签只给最靠前的几个 + 当前选中机场，且不再叠在中心大枢纽上
    labels = nodes.nlargest(min(label_top, len(nodes)), size_col)
    if focus_id is not None and focus_id in valid_ids:
        labels = pd.concat([labels, nodes[nodes["airport_id"] == focus_id]]) \
                   .drop_duplicates("airport_id")
    text = alt.Chart(labels).mark_text(dy=-12, fontSize=10, color=INK,
                                       fontWeight="bold").encode(
        x="x:Q", y="y:Q", text="iata:N")
    layers.append(text)

    if focus_id is not None and focus_id in valid_ids:
        ring = alt.Chart(nodes[nodes["airport_id"] == focus_id]).mark_circle(
            filled=False, stroke=AMBER, strokeWidth=2.6, size=420).encode(
            x="x:Q", y="y:Q")
        layers.append(ring)

    # 图例文字色不写死，交给 Streamlit 内置主题跟随浅/深主题
    chart = alt.layer(*layers).properties(height=height, **_BG).configure_view(
        stroke=None, fill="transparent").configure_legend(
        labelFontSize=10, titleFontSize=11)
    return chart, nodes


def bar_chart(df, value_col, label_col, title, height=460, color=BRAND):
    d = df.copy()
    d[value_col] = _numeric(d[value_col])
    return (alt.Chart(d).mark_bar(cornerRadiusEnd=3, color=color).encode(
        x=alt.X(f"{value_col}:Q", title=value_col,
                axis=alt.Axis(gridColor=GRID)),
        y=alt.Y(f"{label_col}:N", title=None, sort="-x"),
        tooltip=[alt.Tooltip(f"{label_col}:N", title="机场"),
                 alt.Tooltip(f"{value_col}:Q", title=title, format=".5f"),
                 alt.Tooltip("iata:N", title="三字码"),
                 alt.Tooltip("utilization:Q", title="利用率", format=".3f")],
    ).properties(title=title, height=height, **_BG))


def scatter_chart(df, height=440):
    d = df.copy()
    for c in ("real_throughput_2023", "coupling", "w_degree", "utilization"):
        d[c] = _numeric(d[c])
    return (alt.Chart(d).mark_circle(opacity=0.78, stroke=EDGE,
                                     strokeWidth=0.8).encode(
        x=alt.X("real_throughput_2023:Q", title="2023 年旅客吞吐量（人次）",
                axis=alt.Axis(format="~s")),
        y=alt.Y("coupling:Q", title="综合耦合权重"),
        size=alt.Size("w_degree:Q", scale=alt.Scale(range=[40, 700]),
                      legend=alt.Legend(title="加权度")),
        color=alt.Color("utilization:Q", scale=alt.Scale(scheme="orangered"),
                        legend=alt.Legend(title="容量利用率")),
        tooltip=[alt.Tooltip("iata:N", title="三字码"),
                 alt.Tooltip("name:N", title="机场"),
                 alt.Tooltip("real_throughput_2023:Q", title="吞吐量", format=",.0f"),
                 alt.Tooltip("design_capacity:Q", title="设计容量", format=",.0f"),
                 alt.Tooltip("coupling:Q", title="耦合权重", format=".4f"),
                 alt.Tooltip("utilization:Q", title="利用率", format=".4f")],
    ).properties(title="吞吐量 × 耦合权重（颜色为容量利用率）",
                 height=height, **_BG))


def vulnerability_chart(vdf, height=420):
    """双轴：剩余最大连通分量 LCC（左） + 连通性下降比例（右）。"""
    d = vdf.copy()
    d["lcc"] = _numeric(d["lcc"])
    d["drop_pct"] = _numeric(d["lcc_drop_ratio"]) * 100
    base = alt.Chart(d).encode(x=alt.X("k:Q", title="移除关键机场数 K",
                                       axis=alt.Axis(tickMinStep=1)))
    line1 = base.mark_line(color=BRAND, strokeWidth=2.5, point=alt.OverlayMarkDef(
        size=70, filled=True, color=BRAND)).encode(
        y=alt.Y("lcc:Q", title="剩余最大连通分量（节点数）",
                axis=alt.Axis(titleColor=BRAND, labelColor=BRAND)),
        tooltip=[alt.Tooltip("k:Q", title="K"),
                 alt.Tooltip("lcc:Q", title="剩余 LCC"),
                 alt.Tooltip("drop_pct:Q", title="下降比例(%)", format=".1f")])
    line2 = base.mark_line(color=AMBER, strokeWidth=2.2, strokeDash=[6, 4],
                           point=alt.OverlayMarkDef(size=60, color=AMBER)).encode(
        y=alt.Y("drop_pct:Q", title="连通性下降比例 (%)",
                axis=alt.Axis(titleColor=AMBER, labelColor=AMBER, orient="right")))
    return alt.layer(line1, line2).resolve_scale(y="independent").properties(
        title="定向移除 Top-K 关键机场后的网络收缩", height=height, **_BG)
