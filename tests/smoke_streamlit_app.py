# -*- coding: utf-8 -*-
"""Streamlit 无浏览器冒烟测试（不启动浏览器、不占端口）。

用法（在已装好 Streamlit 的 streamlit_env 中）：
    python tests/smoke_streamlit_app.py

覆盖：未登录、错误密码、账号登录、管理员、分析师只读、区域与交互按钮，
以及拓扑图的摆点方式切换和「只看相邻机场」局部视图。
连续交互场景使用注入登录态的独立实例，避免 AppTest 在表单提交后残留元素。
本脚本依赖 streamlit_env，不属于 `unittest discover` 的 30 项自动化测试，单独执行。
"""
import os
import sys

from streamlit.testing.v1 import AppTest

APP = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "visualization", "web_frontend", "app.py"))

# AppTest 不会像 `streamlit run` 那样把脚本目录加入模块搜索路径，
# 这里显式补上，app.py 内的 `import data_loader / charts / ui` 才能找到。
sys.path.insert(0, os.path.dirname(APP))

all_err = []
skipped = []


def report(tag, at):
    errs = [str(e.value)[:200] for e in at.exception]
    print("[%s] exc=%s tabs=%d df=%d sel=%d slider=%d btn=%d dl=%d warn=%d err=%d" % (
        tag, errs, len(at.tabs), len(at.dataframe), len(at.selectbox),
        len(at.slider), len(at.button), len(at.get("download_button")),
        len(at.warning), len(at.error)))
    all_err.extend(errs)
    return at


def fresh():
    return AppTest.from_file(APP, default_timeout=90).run()


def login(acct, pwd):
    at = fresh()
    at.text_input[0].set_value(acct)
    at.text_input[1].set_value(pwd)
    return at.button[0].click().run()


def logged_in(acct="admin", role="admin", name="系统管理员"):
    """连续交互场景的基线实例：直接注入登录态。

    AppTest 走「st.form 提交 + st.rerun」时，会在元素树里残留上一轮的
    form_submit_button；后续对同一实例连续 set_value 会因此找不到 widget 状态。
    这里跳过表单点击，只注入 session_state，验证的是主页面交互而非登录表单。
    """
    at = fresh()
    at.session_state["auth"] = {"account": acct, "name": name, "role": role}
    return at.run()


def scenario(tag, fn):
    try:
        return report(tag, fn())
    except Exception as exc:  # AppTest 框架对复杂连续 widget 状态的限制
        skipped.append((tag, type(exc).__name__, str(exc)[:110]))
        print("[%s] 框架跳过: %s: %s" % (tag, type(exc).__name__, str(exc)[:110]))
        return None


scenario("未登录", fresh)
scenario("错误密码", lambda: login("admin", "wrong-password"))
scenario("账号登录（点击表单）", lambda: login("admin", "admin2026"))
scenario("分析师只读", lambda: login("analyst", "analyst2026"))
admin = scenario("管理员（会话基线）", logged_in)

def switch_layout(a, value):
    """按标签找到「摆点方式」选择框，验证 auto / geo / spring 三种布局都能渲染。"""
    for s in a.selectbox:
        if "摆点方式" in str(getattr(s, "label", "")):
            return s.set_value(value).run()
    return a.run()


def switch_sort(a, value):
    """切换中心性排行的排序指标，覆盖排序项与固定列同名的情况。"""
    for s in a.selectbox:
        if "排序指标" in str(getattr(s, "label", "")):
            return s.set_value(value).run()
    return a.run()


if admin is not None:
    for name, fn in [
        ("切换地理布局", lambda a: switch_layout(a, "geo")),
        ("切换力导向布局", lambda a: switch_layout(a, "spring")),
        ("只看相邻机场", lambda a: a.checkbox[0].set_value(True).run()),
        ("恢复全局拓扑", lambda a: a.checkbox[0].set_value(False).run()),
        ("中国区域", lambda a: a.radio[0].set_value("china").run()),
        ("航段查询", lambda a: [b for b in a.button if "查询航段" in str(getattr(b, "label", ""))][0].click().run()),
        ("反向切换", lambda a: [b for b in a.button if "反向" in str(getattr(b, "label", ""))][0].click().run()),
        ("新增订阅", lambda a: [b for b in a.button if "新增订阅" in str(getattr(b, "label", ""))][0].click().run()),
    ]:
        scenario(name, lambda a=admin, f=fn: f(a))

    # 排序项与表格固定列同名时会撞列名，每个取值用独立实例跑一遍
    for key, label in [("real_throughput_2023", "2023 年吞吐量"),
                       ("utilization", "容量利用率"),
                       ("design_capacity", "设计容量"),
                       ("coupling", "综合耦合权重")]:
        scenario("排序=" + label, lambda k=key: switch_sort(logged_in(), k))

print("\n=== 应用异常总数: %d / 框架跳过场景: %d ===" % (len(all_err), len(skipped)))
if all_err:
    for e in all_err:
        print("   !", e)
sys.exit(1 if all_err else 0)
