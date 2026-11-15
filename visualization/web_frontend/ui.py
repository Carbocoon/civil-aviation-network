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
"""
import inspect

import streamlit as st

# --- 品牌色：深浅背景上都能读（用于图形、色条、大字，不用于小号正文） ---
BRAND = "#2a7cc0"
ACCENT = "#1f9fbd"
AMBER = "#e08a3c"
RED = "#d9695f"
GREEN = "#3fa17a"

# --- hero 专用深蓝渐变（独立色块 + 白字，任何主题下都清楚） ---
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
.stApp {{
  /* 结构色由当前文字色派生，自动适配浅/深主题 */
  --card: rgba(125,145,170,.10);
  --card: color-mix(in srgb, currentColor 7%, transparent);
  --line: rgba(125,145,170,.30);
  --line: color-mix(in srgb, currentColor 17%, transparent);
  --muted: rgba(125,145,170,.95);
  --muted: color-mix(in srgb, currentColor 64%, transparent);
  --brand:{BRAND}; --accent:{ACCENT}; --amber:{AMBER};
  --red:{RED}; --green:{GREEN};
  --soft:rgba(31,159,189,.10); --soft-line:rgba(31,159,189,.34);
  --warn:rgba(224,138,60,.11); --warn-line:rgba(224,138,60,.36);
}}
html, body, [class*="css"] {{
  font-family:"Microsoft YaHei","PingFang SC","Segoe UI",sans-serif;
}}
.block-container {{ padding-top:1.5rem; padding-bottom:3rem; max-width:1500px; }}
#MainMenu {{visibility:hidden;}} footer {{visibility:hidden;}}

.hero {{
  background:linear-gradient(118deg,{HERO_FROM} 0%,{HERO_MID} 58%,{ACCENT} 100%);
  border:1px solid rgba(255,255,255,.10);
  border-radius:18px; padding:26px 32px 24px; color:#fff;
  box-shadow:0 10px 28px rgba(0,0,0,.18); margin-bottom:20px;
}}
.hero .eyebrow {{ font-size:12px; letter-spacing:.22em; opacity:.78; margin-bottom:8px; }}
.hero h1 {{ font-size:27px; font-weight:700; margin:0 0 8px; letter-spacing:.01em; }}
.hero p {{ font-size:13.5px; opacity:.88; margin:0; line-height:1.7; }}
.hero .badges {{ margin-top:14px; }}
.hero .badges span {{
  display:inline-block; background:rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.22);
  border-radius:999px; padding:4px 12px; font-size:11.5px; margin-right:8px; margin-top:5px;
}}

.kpi {{
  position:relative; background:var(--card); border:1px solid var(--line);
  border-radius:14px; padding:17px 18px 15px; min-height:104px;
  box-shadow:0 3px 12px rgba(0,0,0,.06); overflow:hidden;
}}
.kpi:before {{ content:""; position:absolute; left:0; top:0; bottom:0; width:4px; background:var(--accent); }}
.kpi.blue:before {{ background:{BRAND}; }} .kpi.cyan:before {{ background:{ACCENT}; }}
.kpi.amber:before {{ background:{AMBER}; }} .kpi.red:before {{ background:{RED}; }}
.kpi.green:before {{ background:{GREEN}; }}
.kpi-label {{ font-size:12px; color:var(--muted); letter-spacing:.03em; }}
.kpi-value {{ font-size:29px; font-weight:700; line-height:1.25; margin:5px 0 2px; color:inherit; }}
.kpi-sub {{ font-size:11.5px; color:var(--muted); }}

.section-title {{
  font-size:16px; font-weight:700; color:inherit;
  border-left:3px solid var(--accent); padding-left:10px; margin:6px 0 14px;
}}

.soft-note, .warn-note {{
  border-radius:10px; padding:10px 14px; font-size:12.5px;
  color:inherit; line-height:1.7; margin:8px 0 14px;
}}
.soft-note {{ background:var(--soft); border:1px solid var(--soft-line); }}
.warn-note {{ background:var(--warn); border:1px solid var(--warn-line); }}

.stTabs [data-baseweb="tab-list"] {{ gap:4px; border-bottom:1px solid var(--line); }}
.stTabs [data-baseweb="tab"] {{
  background:transparent; border-radius:8px 8px 0 0; padding:9px 13px;
  font-size:13px; color:var(--muted); border:none;
}}
.stTabs [aria-selected="true"] {{
  color:inherit !important; font-weight:700; border-bottom:2px solid var(--accent) !important;
}}
div[data-testid="stSidebar"] {{ border-right:1px solid var(--line); }}
div[data-testid="stSidebar"] .block-container {{ padding-top:1.4rem; }}
.side-brand {{ font-size:15px; font-weight:700; color:var(--brand); margin-bottom:2px; }}
.side-sub {{ font-size:11px; color:var(--muted); margin-bottom:14px; }}
.stButton>button, .stDownloadButton>button {{
  border-radius:9px; border:1px solid var(--line); font-size:13px;
}}
.stButton>button[kind="primary"], .stDownloadButton>button[kind="primary"] {{
  background:{BRAND}; border-color:{BRAND}; color:#fff;
}}
div[data-testid="stMetricValue"] {{ font-size:24px; font-weight:700; color:var(--brand); }}
hr {{ border-color:var(--line); }}
</style>
"""


def apply_style():
    """注入自适应 CSS。

    图表配色不在这里注册自定义 Altair 主题：Streamlit 自带主题会跟随浅/深主题
    设置坐标轴与图例文字色（Altair 5.5 起旧主题 API 已弃用），页面只需要保证
    背景透明与图形自身颜色中性即可，见 charts.py。
    """
    st.markdown(CSS, unsafe_allow_html=True)


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


def kpi(label, value, sub="", tone="blue"):
    return (f'<div class="kpi {tone}"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-value">{value}</div>'
            f'<div class="kpi-sub">{sub}</div></div>')


def kpi_row(items):
    """items: [(label, value, sub, tone), ...]"""
    cols = st.columns(len(items))
    for col, (label, value, sub, tone) in zip(cols, items):
        col.markdown(kpi(label, value, sub, tone), unsafe_allow_html=True)


def section(title):
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)


def note(text, kind="soft"):
    cls = "warn-note" if kind == "warn" else "soft-note"
    st.markdown(f'<div class="{cls}">{text}</div>', unsafe_allow_html=True)
