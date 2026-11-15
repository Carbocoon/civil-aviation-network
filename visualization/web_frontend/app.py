# -*- coding: utf-8 -*-
"""民航航线网络结构分析系统 · Streamlit 可视化看板。

运行（本目录下执行；base 与 streamlit_env 均可，自动适配 Streamlit 1.45 / 1.52+）：
    streamlit run app.py

网络拓扑默认按 airports.dat 的真实经纬度摆点，
力导向仅作为可选项 / 无坐标时的回退。
覆盖题目十项需求的可视化部分：
  1 网络拓扑  2 耦合权重配置（管理员可调，敏感性分析）  3 中心性排行
  4 瓶颈识别  5 吞吐量排序与耦合对比  6 脆弱性评估
  7 容量流量下钻（机场 + 航段两级）  8 报表导出
  9 容量饱和预警订阅  10 区域子图筛选（全局 / 中国含港澳台）

数据源：算法产出的 data/processed/ 结果文件。展示层不实现算法逻辑；
容量饱和预警为正式功能，高吞吐量预警仅作辅助参考。
依赖仅用 streamlit / pandas / numpy / altair；界面自适应浅色 / 深色主题，
宽度参数按 Streamlit 版本自动选择（ui.STRETCH），不需要为不同环境改代码。
"""
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

import data_loader as dl
import ui
from charts import (network_chart, bar_chart, scatter_chart,
                    vulnerability_chart)

# ---------------------------------------------------------------- 常量
ALPHA_DEFAULT, BETA_DEFAULT = 0.6, 0.4
TAU1, TAU2 = 0.75, 0.90

# 演示账号：课程项目内的轻量角色控制，非生产鉴权；生产环境应对接统一身份认证。
USERS = {
    "admin": {"password": "admin2026", "role": "admin", "name": "系统管理员"},
    "analyst": {"password": "analyst2026", "role": "analyst", "name": "航线网络分析师"},
}

METRIC_LABELS = {
    "coupling": "综合耦合权重", "w_degree": "加权度（度中心性）",
    "w_out": "出度中心性", "w_in": "入度中心性", "closeness": "接近中心性",
    "betweenness": "介数中心性", "pagerank": "PageRank", "bottleneck": "节点瓶颈分",
    "utilization": "容量利用率", "real_throughput_2023": "2023 年旅客吞吐量",
    "design_capacity": "设计容量",
}
NUM_COLS = list(METRIC_LABELS) + ["w_out", "w_in"]

st.set_page_config(page_title="民航航线网络结构分析看板", page_icon="✈",
                   layout="wide", initial_sidebar_state="expanded")
ui.apply_style()


# ---------------------------------------------------------------- 登录
def login_view():
    ui.hero(
        "民航航线网络结构分析系统",
        "以机场为点、航段为边、吞吐量与容量为权，展示中心性、结构性瓶颈、脆弱性与容量饱和预警。"
        "请先登录后进入看板。",
        ["HDFS · Hive · Spark SQL · Python", "2023 真实吞吐量 / 设计容量", "课程设计项目"],
    )
    blank, card, _ = st.columns([1, 1.25, 1])
    with card:
        st.markdown("#### 账号登录")
        with st.form("login_form"):
            username = st.text_input("账号", placeholder="admin 或 analyst")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("进入系统", type="primary",
                                              **ui.STRETCH)
        if submitted:
            user = USERS.get((username or "").strip().lower())
            if user and user["password"] == password:
                st.session_state["auth"] = {
                    "account": username.strip().lower(),
                    "name": user["name"], "role": user["role"],
                }
                st.rerun()
            else:
                st.error("账号或密码不正确，请使用下方演示账号。")
        ui.note(
            "演示账号（课程项目内的轻量角色控制，非生产鉴权）：<br>"
            "<b>管理员</b> admin / admin2026 —— 可调整耦合权重参数；<br>"
            "<b>分析师</b> analyst / analyst2026 —— 只读浏览全部看板。",
        )


if "auth" not in st.session_state:
    st.session_state["auth"] = None
if not st.session_state["auth"]:
    login_view()
    st.stop()

AUTH = st.session_state["auth"]
IS_ADMIN = AUTH["role"] == "admin"


# ---------------------------------------------------------------- 侧边栏
with st.sidebar:
    st.markdown('<div class="side-brand"><i>✈</i>航线网络分析</div>'
                '<div class="side-sub">Civil Aviation Network Analytics</div>',
                unsafe_allow_html=True)
    st.markdown(
        f'<div class="side-who"><b>{AUTH["name"]}</b>'
        f'<span>账号 {AUTH["account"]} · '
        f'{"管理员（可配置权重）" if IS_ADMIN else "分析师（只读）"}</span></div>',
        unsafe_allow_html=True)
    if st.button("退出登录", **ui.STRETCH):
        st.session_state["auth"] = None
        st.rerun()

    ui.side_head("数据范围")
    label = st.radio("区域子图", ["global", "china"],
                     format_func=lambda x: "全球网络" if x == "global" else "中国（含港澳台）",
                     label_visibility="collapsed")

    ui.side_head("视图控制 · 拓扑图")
    top_n = st.slider("展示节点数（按耦合权重取 Top）", 30, 200, 90, step=10)
    layout_mode = st.selectbox(
        "摆点方式", ["auto", "geo", "spring"],
        format_func=lambda x: {"auto": "自动（优先真实经纬度）",
                               "geo": "真实经纬度（地理分布）",
                               "spring": "力导向（按连线聚簇）"}[x],
        label_visibility="collapsed")
    edge_limit = st.slider("最多画几条航段", 50, 400, 150, step=25)
    focus_only = st.checkbox("只看所选机场的相邻机场", value=False,
                             help="把「网络拓扑」页切换成以选中机场为中心的局部视图")

    ui.side_head("口径说明")
    with st.expander("算法参数（已冻结）", expanded=False):
        st.caption(f"耦合权重 = α×利用率 + β×中心性，α={ALPHA_DEFAULT}、β={BETA_DEFAULT}")
        st.caption(f"预警阈值：τ1={TAU1}（一级）、τ2={TAU2}（二级）")
        st.caption("介数抽样 k=800（仅全局大图）")
        st.caption("容量饱和预警为正式功能，高吞吐量预警仅为辅助参考。")
    st.caption("数据源：算法输出的 data/processed/ 结果文件")


# ---------------------------------------------------------------- 数据
@st.cache_data(ttl=300, show_spinner=False)
def load_all(region):
    return {
        "airport": dl.load_airport_metrics(region)[0],
        "airport_path": dl.load_airport_metrics(region)[1],
        "edge": dl.load_edge_bottleneck(region)[0],
        "edge_iata": dl.load_edges_with_iata(region),
        "sat": dl.load_saturation_warnings(region)[0],
        "tp": dl.load_throughput_warnings(region)[0],
        "vuln": dl.load_vulnerability(region)[0],
        "vuln_path": dl.load_vulnerability(region)[1],
        # 真实经纬度只用于拓扑图摆点，不进入结果列契约
        "coords": dl.load_airport_coordinates(),
    }


data = load_all(label)
airport_df = data["airport"].copy()
edge_df = data["edge"].copy()
edge_iata = data["edge_iata"].copy()
sat_df = data["sat"].copy()
tp_df = data["tp"].copy()
vuln = data["vuln"]

for df in (airport_df, edge_df, edge_iata, sat_df, tp_df):
    for c in NUM_COLS + ["weight", "edge_coupling", "throughput_2023", "level"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

ui.header(
    "民航航线网络结构分析系统 · 可视化看板",
    "展示层只读算法结果，不实现算法逻辑 · 容量饱和按「2023 真实吞吐量 ÷ 真实设计容量」判定",
    [("区域：" + ("全球网络" if label == "global" else "中国（含港澳台）"), True),
     "数据源 data/processed",
     f"口径 α={ALPHA_DEFAULT} / β={BETA_DEFAULT}",
     f"登录：{AUTH['name']}"],
)

if airport_df.empty:
    st.warning("暂未读取到算法结果数据。请先在仓库根运行 `python -m algorithm.engine` "
               "生成 `data/processed/`，或向组长索取结果样例；看板已保留空表容错。")
    st.stop()

ui.kpi_row([
    ("机场节点", f"{len(airport_df):,}", "当前区域图节点数", "blue"),
    ("航段记录", f"{len(edge_df):,}", "有向加权边", "cyan"),
    ("容量饱和预警", f"{len(sat_df):,}", "基于真实设计容量", "red", "正式", "hot"),
    ("高吞吐量机场", f"{len(tp_df):,}", "仅衡量繁忙度", "amber", "辅助", "warm"),
])

def _native(x):
    """把 numpy 标量转成 Python 原生值，避免 Streamlit 组件写入 protobuf 时报错。"""
    return x.item() if hasattr(x, "item") else x


def _code(row):
    """机场三字码；CSV 空值会读成 NaN，统一转成可显示的字符串。"""
    iata = row.get("iata")
    if iata is None or pd.isna(iata) or not str(iata).strip():
        return str(row["airport_id"])
    return str(iata).strip()


NAME_BY_ID = {str(r["airport_id"]): _code(r) for _, r in airport_df.iterrows()}


tab_topo, tab_rank, tab_compare, tab_bottleneck, tab_warn, tab_vuln, \
    tab_drill, tab_weight, tab_export = st.tabs([
        "① 网络拓扑", "② 中心性排行", "③ 吞吐·耦合", "④ 瓶颈识别", "⑤ 容量预警",
        "⑥ 脆弱性", "⑦ 容量流量下钻", "⑧ 权重配置", "⑨ 报表导出",
    ])

# ---------------------------------------------------------------- 1 网络拓扑
with tab_topo:
    ui.section("航线网络拓扑 · 节点大小 / 颜色 / 边宽均可切换")
    c1, c2, c3 = st.columns([1, 1, 1.4])
    size_col = c1.selectbox("节点大小映射", ["coupling", "real_throughput_2023",
                                             "w_degree", "betweenness", "pagerank"],
                            format_func=lambda k: METRIC_LABELS[k])
    color_col = c2.selectbox("节点颜色映射", ["utilization", "coupling",
                                              "betweenness", "pagerank"],
                             format_func=lambda k: METRIC_LABELS[k])
    options = [_native(x) for x in
               airport_df.sort_values("coupling", ascending=False)["airport_id"].tolist()]
    focus_id = c3.selectbox("选择机场查看节点明细", options,
                            format_func=lambda i: NAME_BY_ID.get(str(i), str(i)))

    # 经纬度只加在拓扑页用的副本上，不污染其它页面与导出结果
    topo_df = dl.attach_coordinates(airport_df, data["coords"])
    ranked_all = topo_df.sort_values("coupling", ascending=False)
    if focus_only and focus_id is not None:
        related = edge_df[(edge_df["src_id"] == focus_id)
                          | (edge_df["dst_id"] == focus_id)]
        keep = (set(related["src_id"].tolist())
                | set(related["dst_id"].tolist()) | {focus_id})
        top_nodes = ranked_all[ranked_all["airport_id"].isin(keep)].head(top_n)
        edge_candidates = related.sort_values("bottleneck", ascending=False)
        scope = f"以 {NAME_BY_ID.get(str(focus_id), str(focus_id))} 为中心的局部视图"
    else:
        top_nodes = ranked_all.head(top_n)
        edge_candidates = edge_df.sort_values("bottleneck", ascending=False)
        scope = f"按耦合权重取 Top {top_n} 节点"
    edge_top = edge_candidates.head(max(edge_limit * 2, 300))

    chart, plotted = network_chart(top_nodes, edge_top, size_col=size_col,
                                   color_col=color_col, focus_id=focus_id,
                                   layout=layout_mode, max_edges=edge_limit,
                                   label_top=5)
    if chart is not None:
        st.altair_chart(chart, **ui.STRETCH)
    used = (plotted["_layout"].iloc[0]
            if plotted is not None and not plotted.empty and "_layout" in plotted
            else "spring")
    layout_txt = ("按机场<b>真实经纬度</b>摆放（位置有含义，枢纽不再堆在中心）"
                  if used == "geo" else
                  "力导向布局（按连线聚簇；当前没有可用的经纬度数据）")
    ui.note(f"<b>{scope}</b> · {layout_txt} · 最多画 {edge_limit} 条航段；"
            f"节点大小 = {METRIC_LABELS[size_col]}，节点颜色 = {METRIC_LABELS[color_col]}，"
            "<b>边宽映射航段权重</b>；橙线为所选机场的关联航段，其余连线已压淡，"
            "只给最靠前的 5 个机场和当前选中机场标三字码。鼠标悬停可看完整指标；"
            "侧边栏可切换摆点方式、连线数量与「只看相邻机场」。")

    if focus_id is not None:
        row = airport_df[airport_df["airport_id"] == focus_id]
        if not row.empty:
            r = row.iloc[0]
            ui.section(f"节点明细 · {r.get('iata', '')} {r.get('name', '')}")
            ui.kpi_row([
                ("2023 吞吐量", f"{r.get('real_throughput_2023') or 0:,.0f}", "人次 / 年", "blue"),
                ("设计容量", f"{r.get('design_capacity') or 0:,.0f}", "人次 / 年", "cyan"),
                ("容量利用率", f"{r.get('utilization') or 0:.2%}", "τ1=0.75 / τ2=0.90", "red"),
                ("耦合权重", f"{r.get('coupling') or 0:.4f}", "综合指标", "green"),
            ])
            detail = pd.DataFrame({
                "指标": ["三字码", "机场名称", "城市", "国家", "加权度", "出度", "入度",
                         "接近中心性", "介数中心性", "PageRank", "节点瓶颈分"],
                "数值": [r.get("iata", ""), r.get("name", ""), r.get("city", ""),
                         r.get("country", ""), r.get("w_degree", ""), r.get("w_out", ""),
                         r.get("w_in", ""), r.get("closeness", ""), r.get("betweenness", ""),
                         r.get("pagerank", ""), r.get("bottleneck", "")],
            })
            detail["数值"] = detail["数值"].astype(str)
            st.dataframe(detail, **ui.STRETCH, hide_index=True)

# ---------------------------------------------------------------- 2 中心性排行
with tab_rank:
    ui.section("机场中心性 / 综合耦合排行")
    c1, c2, c3 = st.columns([1.4, 1, 0.7])
    sort_col = c1.selectbox("排序指标", list(METRIC_LABELS.keys()),
                            format_func=lambda k: METRIC_LABELS[k])
    keyword = c2.text_input("检索机场名称或三字码", placeholder="如 SHA / 虹桥")
    page_size = c3.selectbox("每页条数", [10, 20, 30, 50], index=1)

    ranked = airport_df.sort_values(sort_col, ascending=False).reset_index(drop=True)
    if keyword.strip():
        kw = keyword.strip().lower()
        ranked = ranked[ranked.apply(
            lambda r: kw in " ".join(str(r.get(c, "")) for c in
                                     ("iata", "name", "city", "country")).lower(), axis=1)]
    total = len(ranked)
    pages = max(1, (total + page_size - 1) // page_size)
    pcol, _gap = st.columns([0.18, 0.82])
    page = pcol.number_input("页码", min_value=1, max_value=pages, value=1, step=1)
    shown = ranked.iloc[(page - 1) * page_size: page * page_size]

    st.altair_chart(bar_chart(ranked.head(30).assign(iata=ranked.head(30)["iata"].fillna("")),
                              sort_col, "name", f"Top 30 · {METRIC_LABELS[sort_col]}",
                              x_title=METRIC_LABELS[sort_col]),
                    **ui.STRETCH)
    st.caption(f"共 {total} 条记录，第 {page}/{pages} 页；排序指标 {METRIC_LABELS[sort_col]}。")
    st.dataframe(ui.zh(shown[["iata", "name", "city", "country", sort_col, "utilization",
                              "real_throughput_2023", "design_capacity"]]),
                 **ui.STRETCH, hide_index=True,
                 column_config={"容量利用率": st.column_config.ProgressColumn(
                     "容量利用率", min_value=0, max_value=1.2, format="%.3f")})

    ui.section("双列排名对比 · 吞吐量排序 vs 耦合指标排序")
    left, right = st.columns(2)
    tp_top = (airport_df.dropna(subset=["real_throughput_2023"])
              .sort_values("real_throughput_2023", ascending=False).head(15)
              [["iata", "name", "real_throughput_2023"]].reset_index(drop=True))
    cp_top = (airport_df.sort_values("coupling", ascending=False).head(15)
              [["iata", "name", "coupling"]].reset_index(drop=True))
    tp_rank = {r["iata"]: i + 1 for i, r in tp_top.iterrows()}
    cp_rank = {r["iata"]: i + 1 for i, r in cp_top.iterrows()}
    tp_top.insert(0, "吞吐排名", range(1, len(tp_top) + 1))
    # 榜单外的机场没有名次；先保留数值用于比较，展示前再统一转成文本，
    # 避免同一列混用 int 与 str 导致 Streamlit/pyarrow 序列化失败。
    tp_top["耦合榜名次"] = tp_top["iata"].map(cp_rank)
    tp_top["名次差异"] = tp_top.apply(
        lambda r: ("持平" if r["耦合榜名次"] == r["吞吐排名"] else
                   ("上升" if pd.notna(r["耦合榜名次"])
                    and r["耦合榜名次"] < r["吞吐排名"] else "下降/榜外")), axis=1)
    tp_top["耦合榜名次"] = tp_top["耦合榜名次"].map(
        lambda v: str(int(v)) if pd.notna(v) else "榜外")
    cp_top.insert(0, "耦合排名", range(1, len(cp_top) + 1))
    cp_top["吞吐榜名次"] = cp_top["iata"].map(tp_rank).map(
        lambda v: str(int(v)) if pd.notna(v) else "榜外")
    with left:
        st.markdown("**按 2023 年旅客吞吐量**")
        st.dataframe(ui.zh(tp_top), **ui.STRETCH, hide_index=True)
    with right:
        st.markdown("**按综合耦合权重**")
        st.dataframe(ui.zh(cp_top), **ui.STRETCH, hide_index=True)
    st.caption("「名次差异」列标出同一机场在两种口径下的排名变化，用于对比"
               "「按吞吐量排序」与「结构+容量耦合」视角的结论差别。")

# ---------------------------------------------------------------- 3 对比
with tab_compare:
    ui.section("吞吐量 × 容量利用率 × 耦合权重")
    cmp_df = airport_df.dropna(subset=["real_throughput_2023", "coupling"])
    cmp_df = cmp_df[cmp_df["real_throughput_2023"] > 0]
    if not cmp_df.empty:
        st.altair_chart(scatter_chart(cmp_df), **ui.STRETCH)
        st.dataframe(ui.zh(cmp_df.sort_values("real_throughput_2023", ascending=False)
                     [["iata", "name", "real_throughput_2023", "design_capacity",
                       "utilization", "coupling", "betweenness"]].head(30)),
                     **ui.STRETCH, hide_index=True,
                     column_config={"容量利用率": st.column_config.ProgressColumn(
                         "容量利用率", min_value=0, max_value=1.2, format="%.3f")})
    else:
        st.info("暂无可对比的吞吐量数据（真实吞吐量覆盖 94 个机场）。")

# ---------------------------------------------------------------- 4 瓶颈
with tab_bottleneck:
    ui.section("结构性瓶颈识别")
    k_pct = st.slider("判定范围：取瓶颈分前 k% 的航段", 1, 20, 5, step=1)
    ui.note("瓶颈分 = 航段介数 × 耦合权重；阈值仅控制本页展示范围，"
            "不改变算法结果。容量利用率≥τ1 且中心性排名靠前的航段优先关注。")
    if not edge_iata.empty:
        n_keep = max(1, int(len(edge_iata) * k_pct / 100))
        edge_show = (edge_iata.sort_values("bottleneck", ascending=False).head(n_keep)
                     [["src_iata", "dst_iata", "weight", "edge_coupling", "bottleneck"]])
        edge_show.columns = ["起点", "终点", "航段权重", "边耦合", "瓶颈分"]
        st.markdown(f"**瓶颈航段（前 {k_pct}%，共 {len(edge_show)} 条）**")
        st.dataframe(edge_show, **ui.STRETCH, hide_index=True)
    else:
        st.info("暂无航段瓶颈数据。")
    st.markdown("**瓶颈机场（按节点瓶颈分降序）**")
    st.dataframe(ui.zh(airport_df.sort_values("bottleneck", ascending=False).head(20)
                 [["iata", "name", "city", "country", "bottleneck", "coupling",
                   "betweenness"]]), **ui.STRETCH, hide_index=True)

# ---------------------------------------------------------------- 5 预警与订阅
with tab_warn:
    ui.section("容量饱和预警（正式功能）")
    ui.note("判定口径：利用率 = 2023 实际旅客吞吐量 ÷ 真实设计容量；"
            "≥0.90 为二级（接近饱和），≥0.75 为一级（偏繁忙）。"
            "缺设计容量的机场不参与判定，结果真实可核查。")
    if not sat_df.empty:
        s = sat_df.copy()
        s["level"] = pd.to_numeric(s["level"], errors="coerce")
        lvl2 = int((s["level"] == 2).sum())
        lvl1 = int((s["level"] == 1).sum())
        ui.kpi_row([
            ("二级预警", lvl2, "接近饱和 ≥0.90", "red"),
            ("一级预警", lvl1, "偏繁忙 ≥0.75", "amber"),
            ("覆盖机场", len(s), "有真实设计容量的机场", "blue"),
            ("阈值口径", "0.75 / 0.90", "τ1 / τ2", "green"),
        ])
        s["预警级别"] = s["level"].map({2: "二级（接近饱和）", 1: "一级（偏繁忙）"})
        st.dataframe(ui.zh(s[["iata", "name", "utilization", "预警级别"]]),
                     **ui.STRETCH, hide_index=True,
                     column_config={"容量利用率": st.column_config.ProgressColumn(
                         "容量利用率", min_value=0, max_value=1.2, format="%.4f")})
    else:
        st.success("当前口径下无容量饱和预警机场。")

    with st.expander("辅助参考：高吞吐量繁忙度预警（非容量饱和度结论）"):
        ui.note("下表仅按 2023 年旅客吞吐量衡量繁忙度，<b>不代表接近设计上限</b>；"
                "饱和判定请以上表为准。", kind="warn")
        if not tp_df.empty:
            st.dataframe(ui.zh(tp_df[["iata", "name", "throughput_2023", "level"]]),
                         **ui.STRETCH, hide_index=True)
        else:
            st.info("暂无高吞吐量繁忙记录。")

    ui.section("预警订阅管理")
    c1, c2, c3 = st.columns([1.3, 1, 1])
    email = c1.text_input("接收邮箱", placeholder="name@example.com")
    sub_level = c2.selectbox("预警级别", ["一级及以上", "仅二级（接近饱和）"])
    sub_region = c3.selectbox("订阅区域", ["全球", "中国（含港澳台）"])
    if st.button("新增订阅", type="primary"):
        if not email or "@" not in email:
            st.error("请填写有效邮箱。")
        else:
            subs = dl.load_subscriptions()
            if not subs.empty and email.strip() in set(subs["email"].astype(str)):
                st.warning("该邮箱已订阅，可在下方列表中删除后重新添加。")
            else:
                new = pd.DataFrame([{"email": email.strip(), "level": sub_level,
                                     "region": sub_region,
                                     "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}])
                dl.save_subscriptions(pd.concat([subs, new], ignore_index=True))
                st.success(f"已订阅：{email.strip()}（{sub_region} / {sub_level}）。")
                st.rerun()
    subs = dl.load_subscriptions()
    if not subs.empty:
        st.dataframe(ui.zh(subs), **ui.STRETCH, hide_index=True)
        del_email = st.selectbox("选择要取消的订阅邮箱", subs["email"].astype(str).tolist())
        if st.button("取消该订阅"):
            dl.save_subscriptions(subs[subs["email"].astype(str) != del_email])
            st.rerun()
    else:
        st.caption("暂无订阅记录。")
    st.caption(f"订阅记录写入项目根 `subscriptions.csv`。当前版本仅在本地登记，"
               "邮件/消息推送为后续版本功能（已在问题跟踪表中登记）。")

# ---------------------------------------------------------------- 6 脆弱性
with tab_vuln:
    ui.section("瓶颈脆弱性评估（定向移除 Top-K 后连通性收缩）")
    if vuln and "by_k" in vuln:
        vdf = pd.DataFrame(vuln["by_k"])
        k_all = [int(k) for k in vdf["k"].tolist()] if "k" in vdf else []
        k_pick = st.multiselect("K 值参数区：选择要对比的移除场景", k_all, default=k_all)
        vdf = vdf[vdf["k"].isin(k_pick)] if k_pick else vdf
        base_lcc = vuln.get("base_lcc", vdf["lcc"].max() if not vdf.empty else 0)
        ui.kpi_row([
            ("原始最大连通分量", f"{base_lcc:,}", "个节点", "blue"),
            ("K=20 时剩余 LCC", f"{int(vdf['lcc'].min()) if not vdf.empty else 0:,}",
             "最严重场景", "amber"),
            ("最大收缩比例",
             f"{(vdf['lcc_drop_ratio'].max() * 100):.1f}%" if not vdf.empty else "—",
             "依赖核心枢纽的程度", "red"),
            ("仿真场景数", len(vdf), "按介数中心性排序移除", "green"),
        ])
        if not vdf.empty:
            st.altair_chart(vulnerability_chart(vdf), **ui.STRETCH)
        st.dataframe(ui.zh(vdf), **ui.STRETCH, hide_index=True)
        ui.note("口径：按介数中心性排名依次移除前 K 个机场，观察最大连通分量（LCC）"
                "的收缩比例；下降越快说明网络越依赖少数核心枢纽。")
    else:
        st.info("暂无脆弱性仿真结果。")

# ---------------------------------------------------------------- 7 下钻
with tab_drill:
    ui.section("容量流量下钻 · 机场级 + 航段级")
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("**机场级下钻**")
        opts = [_native(x) for x in
                airport_df.sort_values("coupling", ascending=False)["airport_id"].tolist()]
        pick = st.selectbox("选择机场", opts,
                            format_func=lambda i: NAME_BY_ID.get(str(i), str(i)), key="drill_airport")
        row = airport_df[airport_df["airport_id"] == pick].iloc[0]
        ui.kpi_row([
            ("年吞吐量", f"{(row.get('real_throughput_2023') or 0) / 10000:,.0f}", "万人次 · 2023 真实值", "blue"),
            ("设计容量", f"{(row.get('design_capacity') or 0) / 10000:,.0f}", "万人次 · 公开来源", "cyan"),
            ("利用率", f"{row.get('utilization') or 0:.3f}", "吞吐 ÷ 容量", "red"),
            ("耦合权重", f"{row.get('coupling') or 0:.3f}", "综合指标", "green"),
        ])
        detail = row[["iata", "name", "city", "country", "w_degree", "closeness",
                      "betweenness", "pagerank", "bottleneck"]].to_frame("数值")
        detail["数值"] = detail["数值"].astype(str)
        detail.index = [ui.label(i) for i in detail.index]
        detail.index.name = "字段"
        st.dataframe(detail, **ui.STRETCH)

    with c2:
        st.markdown("**航段级下钻（按起降机场三字码查询）**")
        if "seg_from" not in st.session_state:
            st.session_state["seg_from"], st.session_state["seg_to"] = "SHA", "PEK"
        s1, s2, s3 = st.columns([1, 1, 0.9])
        src = s1.text_input("起点三字码", value=st.session_state["seg_from"],
                            key="in_seg_from").strip().upper()
        dst = s2.text_input("终点三字码", value=st.session_state["seg_to"],
                            key="in_seg_to").strip().upper()
        if s3.button("反向", **ui.STRETCH):
            st.session_state["seg_from"], st.session_state["seg_to"] = dst, src
            st.rerun()
        st.session_state["seg_from"], st.session_state["seg_to"] = src, dst
        if st.button("查询航段", type="primary", **ui.STRETCH):
            hit = pd.DataFrame()
            if not edge_iata.empty:
                hit = edge_iata[(edge_iata["src_iata"].astype(str).str.upper() == src) &
                                (edge_iata["dst_iata"].astype(str).str.upper() == dst)]
            if hit.empty:
                st.warning(f"未找到航段 {src} → {dst}，请检查三字码或改用「反向」按钮。")
            else:
                e = hit.iloc[0]
                # 航段流量按始发机场真实吞吐量依航段权重分摊估算（口径与 ETL 一致）
                src_rows = airport_df[airport_df["iata"].astype(str).str.upper() == src]
                if not src_rows.empty:
                    a = src_rows.iloc[0]
                    out_sum = edge_iata[edge_iata["src_iata"].astype(str).str.upper() == src]["weight"].sum()
                    share = (float(e["weight"]) / out_sum) if out_sum else 0.0
                    seg_flow = (a.get("real_throughput_2023") or 0) * share
                    seg_cap = (a.get("design_capacity") or 0) * share
                else:
                    seg_flow = seg_cap = 0
                ui.kpi_row([
                    ("航段权重", f"{e.get('weight') or 0:,.0f}", "频次 / 估算客流", "blue"),
                    ("估算流量", f"{seg_flow:,.0f}", "按频次分摊", "cyan"),
                    ("估算容量", f"{seg_cap:,.0f}", "按频次分摊", "amber"),
                    ("瓶颈分", f"{e.get('bottleneck') or 0:.4f}", "结构性瓶颈", "red"),
                ])
                seg_detail = pd.DataFrame({
                    "字段": ["起点", "终点", "航段权重", "边耦合", "瓶颈分"],
                    "数值": [e["src_iata"], e["dst_iata"], e["weight"],
                             e["edge_coupling"], e["bottleneck"]]})
                seg_detail["数值"] = seg_detail["数值"].astype(str)
                st.dataframe(seg_detail, **ui.STRETCH, hide_index=True)
        ui.note("逐航段实际客流无公开数据源，此处按「始发机场真实年吞吐量 × 该航段频次占比」"
                "估算流量与容量，仅用于相对比较；容量饱和预警仍以机场级真实数据为准。")

# ---------------------------------------------------------------- 8 权重配置
with tab_weight:
    ui.section("中心性 / 容量耦合权重配置（需求 2）")
    if not IS_ADMIN:
        ui.note("当前为<b>分析师（只读）</b>角色，权重参数仅可查看。"
                "如需调整，请使用管理员账号 admin 登录。", kind="warn")
        st.write(f"α = {ALPHA_DEFAULT}（容量利用率权重）　β = {BETA_DEFAULT}（中心性权重）")
        st.write(f"τ1 = {TAU1}（一级预警）　τ2 = {TAU2}（二级预警）　介数抽样 k = 800")
    else:
        c1, c2 = st.columns([1.4, 1])
        alpha = c1.slider("α · 容量利用率权重", 0.10, 0.90, ALPHA_DEFAULT, step=0.05)
        beta = round(1.0 - alpha, 2)
        c2.metric("β · 中心性权重（自动互补）", f"{beta:.2f}")
        top_k_pct = st.slider("瓶颈判定：中心性排名前 k%", 1, 30, 10, step=1)
        if st.button("恢复默认口径"):
            alpha, beta, top_k_pct = ALPHA_DEFAULT, BETA_DEFAULT, 10
            st.rerun()
        ui.note("此处为<b>看板内敏感性分析参数</b>，用于观察权重变化对机场排名的影响；"
                "不会改写 <code>algorithm/config.py</code> 中已冻结的正式口径"
                "（α=0.6、β=0.4、τ1=0.75、τ2=0.90），算法输出的结果文件始终以正式口径为准。")

        sens = airport_df.copy()
        u = pd.to_numeric(sens["utilization"], errors="coerce").fillna(0)
        c = pd.to_numeric(sens["pagerank"], errors="coerce").fillna(0)
        u_n = (u - u.min()) / (u.max() - u.min()) if u.max() > u.min() else u * 0
        c_n = (c - c.min()) / (c.max() - c.min()) if c.max() > c.min() else c * 0
        sens["sens"] = alpha * u_n + beta * c_n
        official = sens.sort_values("coupling", ascending=False).head(10)[["iata", "name", "coupling"]]
        official.insert(0, "正式口径排名", range(1, len(official) + 1))
        trial = sens.sort_values("sens", ascending=False).head(10)[["iata", "name", "sens"]]
        trial.insert(0, "当前参数排名", range(1, len(trial) + 1))
        l, r = st.columns(2)
        with l:
            st.markdown("**正式口径 Top10（α=0.6 / β=0.4）**")
            st.dataframe(ui.zh(official), **ui.STRETCH, hide_index=True)
        with r:
            st.markdown(f"**当前参数 Top10（α={alpha:.2f} / β={beta:.2f}）**")
            st.dataframe(ui.zh(trial), **ui.STRETCH, hide_index=True)
        diff = len(set(official["iata"]) ^ set(trial["iata"]))
        st.caption(f"两榜交集变化 {diff} 个机场；瓶颈判定范围取中心性前 {top_k_pct}%。"
                   "参数仅在本页生效，刷新或切换角色后回到默认口径。")

# ---------------------------------------------------------------- 9 导出
with tab_export:
    ui.section("分析报表导出（需求 8）")
    c1, c2, c3 = st.columns(3)
    c1.download_button("下载机场指标表（CSV）",
                       airport_df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"{label}_airport_metrics.csv", mime="text/csv",
                       **ui.STRETCH)
    c2.download_button("下载容量饱和预警（CSV）",
                       sat_df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"{label}_saturation_warnings.csv", mime="text/csv",
                       **ui.STRETCH)
    c3.download_button("下载航段瓶颈表（CSV）",
                       edge_iata.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"{label}_edge_bottleneck.csv", mime="text/csv",
                       **ui.STRETCH)
    st.caption("导出内容与当前区域筛选一致，UTF-8-SIG 编码，Excel 打开中文不乱码。")

    ui.section("数据源与联调信息")
    st.dataframe(pd.DataFrame({
        "结果文件": ["机场指标", "航段瓶颈", "容量饱和预警", "高吞吐量预警", "脆弱性仿真"],
        "路径": [data["airport_path"], dl._proc_path(f"{label}_edge_bottleneck.csv"),
                 dl._proc_path(f"{label}_saturation_warnings.csv"),
                 dl._proc_path(f"{label}_throughput_warnings.csv"),
                 data["vuln_path"]],
    }), **ui.STRETCH, hide_index=True)
    ui.note("本看板只读算法结果，不写死本机绝对路径：优先按环境变量 "
            "<code>CIVIL_AVIATION_PROJECT_ROOT</code> 定位，否则逐级向上查找 "
            "<code>data/processed</code>。切换到 Hive 数据源后输出目录不变。")

st.divider()
st.caption("基于 Hive 的民航航线网络结构分析系统 · "
           "数据源：OpenFlights + 2023 年真实旅客吞吐量 / 设计容量公开数据")
