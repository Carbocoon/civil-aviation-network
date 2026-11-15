# -*- coding: utf-8 -*-
"""界面样式与小组件：自适应浅色 / 深色主题（不依赖外部字体/CDN）。

自适应的做法：
  1. 不覆盖 Streamlit 自己的页面背景和正文文字色，主题由 Streamlit（或系统偏好）决定；
  2. 卡片、边框、次要文字等结构色用 color-mix(currentColor ...) 从当前文字色派生，
     浅色主题下自动得到深色半透明、深色主题下自动得到浅色半透明，无需检测主题；
     老浏览器回退到中性半透明灰，同样两边可用；
  3. 品牌色选用在白底与黑底上都有足够对比度的中亮色，不随主题切换；
  4. Altair 图表背景透明，坐标轴 / 图例文字交给 Streamlit 内置主题（自动跟随深浅），
     图形自身颜色用中性色，避免深色主题下出现白底黑字。

版式约定（2026-11 改版）：
  · 顶部由大横幅改为 56px 细条，把首屏留给数据；
  · 内容区最大宽度 1560px，间距按 8px 栅格，字阶 11/12/13/14/15/20/30；
  · 标签页改为圆角胶囊，选中态用品牌色淡底，不再抢视线；
  · 表格、输入框、折叠面板统一 10~12px 圆角与 1px 描边。
"""
import inspect

import streamlit as st

# --- 品牌色：深浅背景上都能读（用于图形、色条、大字，不用于小号正文） ---
BRAND = "#2a7cc0"
ACCENT = "#1f9fbd"
AMBER = "#e08a3c"
RED = "#d9695f"
GREEN = "#3fa17a"

# --- hero 专用深蓝渐变（登录页使用；独立色块 + 白字，任何主题下都清楚） ---
HERO_FROM = "#123a6b"
HERO_MID = "#0e5d8a"

# --- 图表用中性色：白底 / 黑底都可读 ---
INK = "#6f8299"                     # 轴标题、图标题
MUTED = "#7b8da3"                   # 刻度、图例
LINE = "rgba(125,145,170,0.32)"     # 轴线、描边
GRID = "rgba(125,145,170,0.18)"     # 网格
EDGE = "rgba(125,145,170,0.48)"     # 网络图连线 / 散点描边


def stretch_kwargs():
    """按 Streamlit 实际 API 生成「撑满容器宽度」的关键字参数。

    1.52+ 用 width="stretch"；1.45~1.51 只有 use_container_width。
    直接看函数签名而不是猜版本号，避免版本判断写错或未来版本又改回来。
    """
    try:
        if "width" in inspect.signature(st.button).parameters:
            return {"width": "stretch"}
    except (TypeError, ValueError):
        pass
    return {"use_container_width": True}


# 模块级常量，app.py 中所有控件以 **ui.STRETCH 传入
STRETCH = stretch_kwargs()

CSS = f"""
<style>
:root, .stApp {{
  --primary-color:#2a7cc0 !important; --primary-color-rgb:42,124,192 !important;
}}
.stApp {{
  /* 结构色由当前文字色派生，自动适配浅/深主题 */
  --primary-color:#2a7cc0; --primary-color-rgb:42,124,192;
  /* 滑块、勾选框等 BaseWeb 组件用到的强调色 */
  --card: rgba(125,145,170,.10);
  --card: color-mix(in srgb, currentColor 5%, transparent);
  --card-2: color-mix(in srgb, currentColor 9%, transparent);
  --line: rgba(125,145,170,.30);
  --line: color-mix(in srgb, currentColor 14%, transparent);
  --line-strong: color-mix(in srgb, currentColor 24%, transparent);
  --muted: rgba(125,145,170,.95);
  --muted: color-mix(in srgb, currentColor 62%, transparent);
  --brand:{BRAND}; --accent:{ACCENT}; --amber:{AMBER};
  --red:{RED}; --green:{GREEN};
  --soft:rgba(31,159,189,.10); --soft-line:rgba(31,159,189,.32);
  --warn:rgba(224,138,60,.10); --warn-line:rgba(224,138,60,.34);
  --shadow:0 1px 2px rgba(0,0,0,.04), 0 8px 24px -14px rgba(0,0,0,.35);
}}

html, body, [class*="css"] {{
  font-family:"Microsoft YaHei","PingFang SC","Segoe UI",-apple-system,sans-serif;
  -webkit-font-smoothing:antialiased;
  font-feature-settings:"tnum" 1;
}}
.block-container {{ padding-top:0.75rem; padding-bottom:3rem; max-width:1560px; }}

/* 收起 Streamlit 自带的页眉 / 菜单 / 状态球，只留内容 */
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], [data-testid="stHeader"] {{ display:none !important; }}

/* ---------- 顶部细条 ---------- */
.app-head {{
  display:flex; align-items:center; justify-content:space-between; gap:16px;
  padding:10px 16px; margin:0 0 14px;
  background:var(--card); border:1px solid var(--line); border-radius:14px;
}}
.app-head .mark {{
  width:34px; height:34px; flex:0 0 34px; border-radius:10px;
  display:flex; align-items:center; justify-content:center;
  font-size:16px; color:#fff;
  background:linear-gradient(135deg,{BRAND},{ACCENT});
  box-shadow:0 6px 16px -8px rgba(42,124,192,.9);
}}
.app-head .head-left {{ display:flex; align-items:center; gap:12px; min-width:0; }}
.app-head .head-title {{ font-size:15px; font-weight:700; line-height:1.3; letter-spacing:.01em; }}
.app-head .head-sub {{ font-size:11.5px; color:var(--muted); line-height:1.4; margin-top:2px; }}
.app-head .head-right {{ display:flex; flex-wrap:wrap; gap:6px; justify-content:flex-end; }}
.chip {{
  display:inline-flex; align-items:center; gap:5px;
  font-size:11.5px; line-height:1; padding:6px 10px; border-radius:999px;
  color:var(--muted); background:var(--card-2); border:1px solid var(--line);
  white-space:nowrap;
}}
.chip b {{ color:inherit; font-weight:600; }}
.chip.on {{ color:var(--brand); border-color:var(--soft-line); background:var(--soft); }}

/* ---------- 登录页 hero ---------- */
.hero {{
  background:linear-gradient(118deg,{HERO_FROM} 0%,{HERO_MID} 58%,{ACCENT} 100%);
  border:1px solid rgba(255,255,255,.10);
  border-radius:18px; padding:26px 32px 24px; color:#fff;
  box-shadow:0 10px 28px rgba(0,0,0,.18); margin-bottom:20px;
}}
.hero .eyebrow {{ font-size:11.5px; letter-spacing:.22em; opacity:.78; margin-bottom:8px; }}
.hero h1 {{ font-size:26px; font-weight:700; margin:0 0 8px; letter-spacing:.01em; }}
.hero p {{ font-size:13px; opacity:.88; margin:0; line-height:1.75; }}
.hero .badges {{ margin-top:14px; }}
.hero .badges span {{
  display:inline-block; background:rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.22);
  border-radius:999px; padding:5px 12px; font-size:11.5px; margin-right:8px; margin-top:5px;
}}

/* ---------- KPI 卡片 ---------- */
.kpi {{
  position:relative; background:var(--card); border:1px solid var(--line);
  border-radius:14px; padding:15px 17px 14px; min-height:100px;
  box-shadow:var(--shadow); overflow:hidden;
  transition:transform .16s ease, border-color .16s ease;
}}
.kpi:hover {{ transform:translateY(-1px); border-color:var(--line-strong); }}
.kpi:before {{ content:""; position:absolute; left:0; top:0; bottom:0; width:3px; background:var(--accent); }}
.kpi.blue:before {{ background:{BRAND}; }} .kpi.cyan:before {{ background:{ACCENT}; }}
.kpi.amber:before {{ background:{AMBER}; }} .kpi.red:before {{ background:{RED}; }}
.kpi.green:before {{ background:{GREEN}; }}
.kpi.ghost {{ background:transparent; border-style:dashed; }}
.kpi.ghost:before {{ background:var(--line-strong); }}
.kpi-head {{ display:flex; align-items:center; justify-content:space-between; gap:8px; }}
.kpi-label {{ font-size:11.5px; color:var(--muted); letter-spacing:.06em; }}
.kpi-tag {{
  font-size:10px; line-height:1; padding:4px 7px; border-radius:999px;
  color:var(--muted); border:1px solid var(--line); background:var(--card-2);
}}
.kpi-tag.hot {{ color:{RED}; border-color:rgba(217,105,95,.38); background:rgba(217,105,95,.10); }}
.kpi-tag.warm {{ color:{AMBER}; border-color:rgba(224,138,60,.38); background:rgba(224,138,60,.10); }}
.kpi-value {{
  font-size:28px; font-weight:700; line-height:1.15; margin:8px 0 4px;
  letter-spacing:-.015em; color:inherit;
}}
.kpi-sub {{ font-size:11.5px; color:var(--muted); line-height:1.5; }}

/* ---------- 区块标题 ---------- */
.section-title {{
  display:flex; align-items:center; gap:9px;
  font-size:15px; font-weight:700; color:inherit;
  margin:14px 0 12px; letter-spacing:.01em;
}}
.section-title:before {{
  content:""; width:3px; height:15px; border-radius:2px;
  background:linear-gradient(180deg,var(--accent),var(--brand));
}}
.section-meta {{ font-size:11.5px; font-weight:400; color:var(--muted); margin-left:2px; }}

/* ---------- 说明条 ---------- */
.soft-note, .warn-note {{
  border-radius:10px; padding:10px 14px; font-size:12px;
  color:inherit; line-height:1.75; margin:6px 0 14px;
}}
.soft-note {{ background:var(--soft); border:1px solid var(--soft-line); border-left-width:3px; }}
.warn-note {{ background:var(--warn); border:1px solid var(--warn-line); border-left-width:3px; }}
</style>
"""

# 第二部分：组件级样式（标签页、侧边栏、表格、输入框），单独注入便于排查
CSS2 = f"""
<style>
/* ---------- 标签页：圆角胶囊 ---------- */
.stTabs [data-baseweb="tab-list"] {{
  gap:6px; border-bottom:1px solid var(--line); padding-bottom:8px; margin-bottom:4px;
  flex-wrap:wrap;
}}
.stTabs [data-baseweb="tab"] {{
  background:transparent; border:none; border-radius:999px;
  padding:7px 14px; font-size:12.5px; color:var(--muted);
  transition:background .15s ease, color .15s ease;
}}
.stTabs [data-baseweb="tab"]:hover {{ background:var(--card-2); color:inherit; }}
.stTabs [aria-selected="true"] {{
  background:var(--soft) !important; color:var(--brand) !important;
  font-weight:700; border-bottom:none !important;
}}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display:none; }}

/* ---------- 侧边栏 ---------- */
div[data-testid="stSidebar"] {{ border-right:1px solid var(--line); }}
div[data-testid="stSidebar"] .block-container {{ padding-top:1.1rem; padding-bottom:2rem; }}
.side-brand {{ display:flex; align-items:center; gap:8px; font-size:14px; font-weight:700; }}
.side-brand i {{
  font-style:normal; width:26px; height:26px; border-radius:8px; color:#fff;
  display:inline-flex; align-items:center; justify-content:center; font-size:13px;
  background:linear-gradient(135deg,{BRAND},{ACCENT});
}}
.side-sub {{ font-size:10.5px; color:var(--muted); margin:4px 0 0 34px; letter-spacing:.04em; }}
.side-h {{
  font-size:10.5px; font-weight:700; letter-spacing:.14em; color:var(--muted);
  margin:14px 0 6px; text-transform:uppercase;
}}
.side-who {{
  font-size:12px; padding:10px 12px; border-radius:10px;
  background:var(--card); border:1px solid var(--line);
}}
.side-who b {{ font-weight:700; }}
.side-who span {{ display:block; font-size:11px; color:var(--muted); margin-top:3px; }}

/* ---------- 表单控件 ---------- */
.stSelectbox div[data-baseweb="select"] > div,
.stMultiSelect div[data-baseweb="select"] > div,
.stTextInput input, .stNumberInput input {{
  border-radius:10px !important; border-color:var(--line) !important;
  font-size:12.5px !important;
}}
.stSlider {{ padding-top:2px; }}
.stButton>button, .stDownloadButton>button, .stFormSubmitButton>button {{
  border-radius:10px; border:1px solid var(--line); font-size:12.5px;
  transition:border-color .15s ease, transform .15s ease;
}}
.stButton>button:hover, .stDownloadButton>button:hover {{ border-color:var(--line-strong); }}
.stButton>button[kind="primary"], .stDownloadButton>button[kind="primary"],
.stFormSubmitButton>button[kind="primary"] {{
  background:{BRAND}; border-color:{BRAND}; color:#fff;
}}
.stButton>button[kind="primary"]:hover {{ filter:brightness(1.06); }}

/* ---------- 折叠面板 ---------- */
div[data-testid="stExpander"] {{
  border:1px solid var(--line); border-radius:12px; background:transparent;
  overflow:hidden;
}}
div[data-testid="stExpander"] summary {{ font-size:12px; padding:8px 12px; }}
div[data-testid="stExpander"] summary:hover {{ background:var(--card-2); }}

/* ---------- 表格 ---------- */
div[data-testid="stDataFrame"] {{
  border:1px solid var(--line); border-radius:12px; overflow:hidden;
  box-shadow:var(--shadow);
}}
div[data-testid="stDataFrame"] [role="columnheader"] {{ font-size:11.5px; font-weight:700; }}
div[data-testid="stDataFrame"] [role="gridcell"] {{ font-size:12.5px; }}
div[data-testid="stDataFrame"] [role="row"]:hover {{ background:var(--card-2); }}

/* ---------- 滑块 / 勾选框：跟随品牌色（Streamlit 默认是红色） ---------- */
[data-testid="stSlider"] div[role="slider"] {{
  background-color:{BRAND} !important; box-shadow:0 0 0 2px {BRAND} !important;
}}
[data-testid="stSlider"] [data-baseweb="slider"] > div > div {{ background:{BRAND} !important; }}
[data-testid="stSlider"] [data-testid="stTickBar"] div {{ background:transparent !important; }}
[data-testid="stCheckbox"] [data-baseweb="checkbox"] div[aria-checked="true"] {{
  background-color:{BRAND} !important; border-color:{BRAND} !important;
}}
[data-testid="stRadio"] [role="radio"][aria-checked="true"] div:first-child {{
  border-color:{BRAND} !important;
}}
[data-testid="stRadio"] [role="radio"][aria-checked="true"] div:first-child > div {{
  background-color:{BRAND} !important;
}}
.stFormSubmitButton>button {{ background:{BRAND} !important; border-color:{BRAND} !important; color:#fff !important; }}

/* ---------- 多选标签统一到品牌色 ---------- */
[data-baseweb="tag"] {{
  background:var(--soft) !important; color:var(--brand) !important;
  border-radius:8px !important; font-size:11.5px !important;
}}
[data-baseweb="tag"] span {{ color:var(--brand) !important; }}

/* ---------- 其它 ---------- */
hr {{ border-color:var(--line); margin:12px 0; }}
div[data-testid="stMetricValue"] {{ font-size:22px; font-weight:700; color:var(--brand); }}
[data-testid="stCaptionContainer"] {{ font-size:11.5px; color:var(--muted); }}
::-webkit-scrollbar {{ width:10px; height:10px; }}
::-webkit-scrollbar-thumb {{
  background:color-mix(in srgb, currentColor 18%, transparent);
  border-radius:999px;
}}
</style>
"""


def apply_style():
    """注入自适应 CSS。

    图表配色不在这里注册自定义 Altair 主题：Streamlit 自带主题会跟随浅/深主题
    设置坐标轴与图例文字色（Altair 5.5 起旧主题 API 已弃用），页面只需要保证
    背景透明与图形自身颜色中性即可，见 charts.py。
    """
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(CSS2, unsafe_allow_html=True)



# --- 表格列名的中文映射（展示层只改显示名，不改数据列契约） ---
COLS = {
    "airport_id": "机场ID", "iata": "三字码", "name": "机场名称",
    "city": "城市", "country": "国家", "province": "省份",
    "w_degree": "加权度", "w_out": "出度", "w_in": "入度",
    "closeness": "接近中心性", "betweenness": "介数中心性", "pagerank": "PageRank",
    "design_capacity": "设计容量", "real_throughput_2023": "2023 年吞吐量",
    "throughput_2023": "2023 年吞吐量", "utilization": "容量利用率",
    "coupling": "综合耦合权重", "bottleneck": "瓶颈分",
    "weight": "航段权重", "edge_coupling": "边耦合",
    "src_id": "起点", "dst_id": "终点", "src_iata": "起点", "dst_iata": "终点",
    "level": "等级", "k": "K 值", "removed": "移除节点数",
    "lcc": "剩余最大连通块", "lcc_drop_ratio": "连通性下降比例",
    "components": "连通块数", "base_lcc": "原始最大连通块",
    "base_components": "原始连通块数", "email": "订阅邮箱",
    "region": "订阅区域", "created_at": "订阅时间", "sens": "当前参数得分",
}


def label(key):
    """单个列名转中文；未收录的原样返回。"""
    return COLS.get(str(key), str(key))


def zh(df):
    """返回把英文列名换成中文的副本（数据本身不动）。"""
    try:
        return df.rename(columns={k: v for k, v in COLS.items() if k in df.columns})
    except Exception:
        return df


def header(title, subtitle, chips=None, filename=None):
    """看板顶部细条（登录后使用），替代占高度的大横幅。"""
    items = []
    for c in chips or []:
        if isinstance(c, (tuple, list)):
            text, on = c[0], len(c) > 1 and c[1]
        else:
            text, on = c, False
        items.append(f'<span class="chip{" on" if on else ""}">{text}</span>')
    spans = "".join(items)
    st.markdown(
        f"""<div class="app-head">
          <div class="head-left">
            <div class="mark">✈</div>
            <div>
              <div class="head-title">{title}</div>
              <div class="head-sub">{subtitle}</div>
            </div>
          </div>
          <div class="head-right">{spans}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def hero(title, subtitle, badges=None):
    tags = "".join(f"<span>{b}</span>" for b in (badges or []))
    st.markdown(
        f"""<div class="hero">
          <div class="eyebrow">CIVIL AVIATION NETWORK ANALYTICS · COURSE PROJECT</div>
          <h1>{title}</h1><p>{subtitle}</p>
          <div class="badges">{tags}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def kpi(label, value, sub="", tone="blue", tag=None, tag_tone=""):
    tag_html = f'<span class="kpi-tag {tag_tone}">{tag}</span>' if tag else ""
    return (f'<div class="kpi {tone}">'
            f'<div class="kpi-head"><div class="kpi-label">{label}</div>{tag_html}</div>'
            f'<div class="kpi-value">{value}</div>'
            f'<div class="kpi-sub">{sub}</div></div>')


def kpi_row(items):
    """items: [(label, value, sub, tone[, tag[, tag_tone]]), ...]"""
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        label, value, sub, tone = item[:4]
        tag = item[4] if len(item) > 4 else None
        tag_tone = item[5] if len(item) > 5 else ""
        col.markdown(kpi(label, value, sub, tone, tag, tag_tone), unsafe_allow_html=True)


def section(title, meta=None):
    extra = f'<span class="section-meta">{meta}</span>' if meta else ""
    st.markdown(f'<div class="section-title">{title}{extra}</div>', unsafe_allow_html=True)


def side_head(text):
    st.markdown(f'<div class="side-h">{text}</div>', unsafe_allow_html=True)


def note(text, kind="soft"):
    cls = "warn-note" if kind == "warn" else "soft-note"
    st.markdown(f'<div class="{cls}">{text}</div>', unsafe_allow_html=True)

