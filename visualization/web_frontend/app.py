# -*- coding: utf-8 -*-
"""民航航线网络结构分析系统 —— 可视化看板（成员C 自研前端）。

运行方式（在 web_frontend/ 目录下）：
    streamlit run app.py

功能对应题目十大需求中的可视化项：
  1 航线网络拓扑展示      2 耦合权重口径展示（α/β、τ1/τ2 只读说明）
  3 机场中心性排行       4 结构性瓶颈航段/机场识别
  5 吞吐量排序与耦合对比 6 瓶颈脆弱性评估
  7 容量流量下钻         8 分析报表导出
  9 容量饱和预警订阅入口 10 区域子图筛选（全局 / 中国含港澳台）

数据源：算法产出 data/processed/ 下的 CSV / JSON；本页面不实现算法逻辑。
"""
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import networkx as nx
import streamlit as st

import data_loader as dl

# ---------- 页面配置 ----------
st.set_page_config(
    page_title="民航航线网络结构分析看板",
    page_icon="✈️",
    layout="wide",
)

# 已定稿口径（algorithm/config.py，不再改动），页面只读展示
ALPHA, BETA = 0.6, 0.4
TAU1, TAU2 = 0.75, 0.90

st.title("✈️ 民航航线网络结构分析系统 · 可视化看板")
st.caption("展示层仅消费算法 ADS 结果表，不实现算法逻辑；容量饱和预警为正式功能，"
            "高吞吐量繁忙度预警仅作辅助参考。")

# ---------- 侧边栏：区域筛选（需求10） ----------
with st.sidebar:
    st.header("筛选与设置")
    label = st.radio("区域子图", ["global", "china"],
                     format_func=lambda x: "全球网络" if x == "global" else "中国（含港澳台）")
    top_n = st.slider("拓扑图展示节点数（按耦合权重取 Top）", 30, 200, 100, step=10)
    st.divider()
    st.markdown("**已定稿算法口径**")
    st.write(f"耦合权重 = α×利用率 + β×中心性，α={ALPHA}，β={BETA}")
    st.write(f"饱和预警阈值：τ1={TAU1}（偏繁忙），τ2={TAU2}（接近饱和）")

# ---------- 读取数据 ----------
airport_df, airport_path = dl.load_airport_metrics(label)
edge_df, edge_path = dl.load_edge_bottleneck(label)
sat_df, sat_path = dl.load_saturation_warnings(label)
tp_df, tp_path = dl.load_throughput_warnings(label)
vuln, vuln_path = dl.load_vulnerability(label)

if airport_df.empty:
    st.warning("暂未读取到算法结果数据。请先运行 `python -m algorithm.engine` 生成 "
               "`data/processed/`，或向组长索取结果样例；本看板已保留空表容错。")
    st.stop()

# ---------- 顶部 KPI ----------
n_nodes = len(airport_df)
n_edges = len(edge_df)
n_sat = len(sat_df)
n_tp = len(tp_df)
k1, k2, k3, k4 = st.columns(4)
k1.metric("机场节点数", n_nodes)
k2.metric("航段记录数", n_edges)
k3.metric("容量饱和预警机场", n_sat)
k4.metric("高吞吐量繁忙（辅助）", n_tp)

# 数值列转类型（空表已被上面拦截）
num_cols = ["w_degree", "closeness", "betweenness", "pagerank",
            "utilization", "coupling", "bottleneck",
            "design_capacity", "real_throughput_2023"]
for c in num_cols:
    if c in airport_df.columns:
        airport_df[c] = pd.to_numeric(airport_df[c], errors="coerce")

tab_topo, tab_rank, tab_compare, tab_bottleneck, tab_warn, tab_vuln, tab_drill = \
    st.tabs(["网络拓扑", "中心性排行", "吞吐-耦合对比", "瓶颈识别",
             "容量饱和预警", "脆弱性评估", "容量流量下钻"])

# ---------- 1. 航线网络拓扑（需求1） ----------
with tab_topo:
    st.subheader("航线网络拓扑（Top 节点 + 关键航段）")
    top_nodes = airport_df.sort_values("coupling", ascending=False).head(top_n)
    G = nx.DiGraph()
    for _, r in top_nodes.iterrows():
        G.add_node(r["airport_id"], name=r.get("name", ""),
                   coupling=r.get("coupling", 0), utilization=r.get("utilization", 0))
    if not edge_df.empty:
        edge_top = edge_df.sort_values("bottleneck", ascending=False).head(top_n)
        for _, e in edge_top.iterrows():
            if e["src_id"] in G and e["dst_id"] in G:
                G.add_edge(e["src_id"], e["dst_id"], weight=e.get("weight", 1),
                           bottleneck=e.get("bottleneck", 0))
    if G.number_of_nodes() > 0:
        pos = nx.spring_layout(G, seed=42, k=0.9)
        # 边
        edge_x, edge_y = [], []
        for u, v in G.edges():
            edge_x += [pos[u][0], pos[v][0], None]
            edge_y += [pos[u][1], pos[v][1], None]
        fig_edge = go.Figure(go.Scatter(x=edge_x, y=edge_y, mode="lines",
                                        line=dict(color="#cccccc", width=1), hoverinfo="none"))
        # 节点
        node_x = [pos[n][0] for n in G.nodes()]
        node_y = [pos[n][1] for n in G.nodes()]
        node_names = [G.nodes[n].get("name") or n for n in G.nodes()]
        node_coupling = [G.nodes[n].get("coupling", 0) for n in G.nodes()]
        node_util = [G.nodes[n].get("utilization", 0) for n in G.nodes()]
        fig_node = go.Scatter(
            x=node_x, y=node_y, mode="markers+text",
            marker=dict(size=[8 + 18 * (c if pd.notna(c) else 0) for c in node_coupling],
                        color=node_util, colorscale="RdYlGn_r",
                        colorbar=dict(title="利用率"), showscale=True),
            text=[n for n in G.nodes()], textposition="top center", textfont=dict(size=9),
            hovertext=[f"{nm}<br>耦合={c:.3f}<br>利用率={u:.3f}"
                       for nm, c, u in zip(node_names, node_coupling, node_util)],
            hoverinfo="text",
        )
        fig_edge.add_trace(fig_node)
        fig_edge.update_layout(showlegend=False, height=560,
                               xaxis=dict(visible=False), yaxis=dict(visible=False))
        st.plotly_chart(fig_edge, use_container_width=True)
        st.caption("节点大小 = 耦合权重；节点颜色 = 容量利用率；连线为瓶颈分 Top 航段。")
    else:
        st.info("拓扑数据不足。")

# ---------- 3. 机场中心性排行（需求3） ----------
with tab_rank:
    st.subheader("机场中心性 / 综合耦合排行")
    metric_options = {
        "综合耦合权重": "coupling",
        "加权度": "w_degree",
        "接近中心性": "closeness",
        "介数中心性": "betweenness",
        "PageRank": "pagerank",
        "节点瓶颈分": "bottleneck",
    }
    pick = st.selectbox("排序指标", list(metric_options.keys()))
    sort_col = metric_options[pick]
    ranked = airport_df.sort_values(sort_col, ascending=False).head(30)
    fig = px.bar(ranked, x=sort_col, y="name", orientation="h",
                 hover_data=["iata", "city", "country", "utilization"],
                 title=f"Top 30 · {pick}", color=sort_col, color_continuous_scale="Blues")
    fig.update_layout(yaxis=dict(autorange="reversed"), height=560)
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(ranked[["iata", "name", "city", "country", sort_col,
                         "utilization", "real_throughput_2023", "design_capacity"]],
                 use_container_width=True, hide_index=True)

# ---------- 5. 吞吐量排序与耦合指标对比（需求5） ----------
with tab_compare:
    st.subheader("吞吐量 × 容量利用率 × 耦合权重对比")
    cmp_df = airport_df.dropna(subset=["real_throughput_2023", "coupling"])
    if not cmp_df.empty:
        fig = px.scatter(
            cmp_df, x="real_throughput_2023", y="coupling",
            size="w_degree", color="utilization", color_continuous_scale="RdYlGn_r",
            hover_data=["iata", "name", "design_capacity", "betweenness"],
            title="吞吐量（x）— 耦合权重（y），颜色为利用率",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(cmp_df.sort_values("real_throughput_2023", ascending=False)
                     [["iata", "name", "real_throughput_2023", "design_capacity",
                       "utilization", "coupling"]].head(30),
                     use_container_width=True, hide_index=True)
    else:
        st.info("暂无可对比的吞吐量数据。")

# ---------- 4. 结构性瓶颈识别（需求4） ----------
with tab_bottleneck:
    st.subheader("结构性瓶颈航段 / 机场")
    st.markdown("**瓶颈航段（按边瓶颈分降序）**")
    if not edge_df.empty:
        st.dataframe(edge_df.head(30), use_container_width=True, hide_index=True)
    else:
        st.info("暂无航段瓶颈数据。")
    st.markdown("**瓶颈机场（按节点瓶颈分降序）**")
    st.dataframe(airport_df.sort_values("bottleneck", ascending=False).head(20)
                 [["iata", "name", "city", "country", "bottleneck", "coupling", "betweenness"]],
                 use_container_width=True, hide_index=True)

# ---------- 9. 容量饱和预警（需求9，主功能） ----------
with tab_warn:
    st.subheader("🚨 容量饱和预警（正式功能）")
    st.caption("判定口径：利用率 = 2023 实际吞吐 ÷ 设计容量；≥0.90 二级（接近饱和），"
               "≥0.75 一级（偏繁忙）。")
    if not sat_df.empty:
        sat_show = sat_df.copy()
        sat_show["level"] = pd.to_numeric(sat_show["level"], errors="coerce")
        st.dataframe(sat_show, use_container_width=True, hide_index=True)
        lvl2 = (sat_show["level"] == 2).sum()
        lvl1 = (sat_show["level"] == 1).sum()
        st.write(f"二级（接近饱和）：**{lvl2}** 个；一级（偏繁忙）：**{lvl1}** 个。")
    else:
        st.success("当前口径下无容量饱和预警机场。")

    with st.expander("辅助参考：高吞吐量繁忙度预警（非容量饱和度结论）"):
        st.warning("下表仅按 2023 年旅客吞吐量衡量繁忙度，不代表接近设计上限；"
                   "饱和判定请以上表为准。")
        if not tp_df.empty:
            st.dataframe(tp_df, use_container_width=True, hide_index=True)
        else:
            st.info("暂无高吞吐量繁忙记录。")

    # 预警订阅入口（需求9）
    st.markdown("#### 预警订阅")
    with st.form("subscribe_form"):
        c1, c2, c3 = st.columns(3)
        email = c1.text_input("接收邮箱")
        sub_level = c2.selectbox("预警级别", ["一级及以上", "仅二级（接近饱和）"])
        sub_region = c3.selectbox("订阅区域", ["全球", "中国（含港澳台）"])
        submitted = st.form_submit_button("订阅预警")
    if submitted:
        if not email or "@" not in email:
            st.error("请填写有效邮箱。")
        else:
            sub_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "subscriptions.csv")
            new_row = pd.DataFrame([{"email": email, "level": sub_level,
                                      "region": sub_region}])
            if os.path.isfile(sub_file):
                new_row.to_csv(sub_file, mode="a", header=False,
                               index=False, encoding="utf-8-sig")
            else:
                new_row.to_csv(sub_file, mode="w", header=True,
                               index=False, encoding="utf-8-sig")
            st.success(f"已订阅：{email}（{sub_region} / {sub_level}）。"
                       "生产环境可对接消息推送。")

# ---------- 6. 脆弱性评估（需求6） ----------
with tab_vuln:
    st.subheader("瓶颈脆弱性评估（定向移除 Top-K 后连通性收缩）")
    if vuln and "by_k" in vuln:
        vdf = pd.DataFrame(vuln["by_k"])
        base_lcc = vuln.get("base_lcc", vdf["lcc"].max() if not vdf.empty else 0)
        st.write(f"原始最大连通分量（LCC）：**{base_lcc}** 个节点")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=vdf["k"], y=vdf["lcc"], mode="lines+markers",
                                 name="剩余 LCC", yaxis="y1"))
        fig.add_trace(go.Scatter(x=vdf["k"], y=vdf["lcc_drop_ratio"] * 100,
                                 mode="lines+markers", name="连通性下降比例(%)", yaxis="y2"))
        fig.update_layout(
            title="移除 Top-K 关键节点后的网络收缩",
            xaxis=dict(title="累计移除节点数 K"),
            yaxis=dict(title="剩余 LCC"),
            yaxis2=dict(title="下降比例(%)", overlaying="y", side="right"),
            height=480,
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(vdf, use_container_width=True, hide_index=True)
    else:
        st.info("暂无脆弱性仿真结果。")

# ---------- 7. 容量流量下钻（需求7） ----------
with tab_drill:
    st.subheader("容量流量下钻")
    name_to_id = {f"{r.get('iata') or r['airport_id']} · {r.get('name', '')}":
                  r["airport_id"] for _, r in airport_df.iterrows()}
    pick_name = st.selectbox("选择机场", list(name_to_id.keys()))
    if pick_name:
        row = airport_df[airport_df["airport_id"] == name_to_id[pick_name]].iloc[0]
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("年吞吐量", row.get("real_throughput_2023", "—"))
        d2.metric("设计容量", row.get("design_capacity", "—"))
        d3.metric("利用率", f"{row.get('utilization', 0):.3f}")
        d4.metric("耦合权重", f"{row.get('coupling', 0):.3f}")
        detail = row[["iata", "name", "city", "country", "w_degree", "closeness",
                      "betweenness", "pagerank", "bottleneck"]]
        st.dataframe(detail.to_frame("数值"), use_container_width=True)

# ---------- 8. 报表导出（需求8） ----------
st.divider()
st.subheader("📤 报表导出")
csv_bytes = airport_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
st.download_button("下载当前区域机场指标表（CSV）", data=csv_bytes,
                   file_name=f"{label}_airport_metrics.csv", mime="text/csv")

with st.expander("数据源文件路径（联调用）"):
    st.write(f"指标表：`{airport_path}`")
    st.write(f"航段瓶颈：`{edge_path}`")
    st.write(f"饱和预警：`{sat_path}`")
    st.write(f"脆弱性：`{vuln_path}`")
