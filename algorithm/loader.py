# -*- coding: utf-8 -*-
"""数据加载：本地原始数据(.dat)、真实吞吐/容量 CSV，以及 Hive 生产模式。

本地模式与 Hive 模式返回同构数据，上层构图与指标计算无需感知数据来源。
切换方式见 algorithm/config.py 文件头的环境变量说明。
"""
import csv
import re
import warnings

from .config import (AIRPORTS_FILE, ROUTES_FILE, THROUGHPUT_FILE,
                     CAPACITY_FILE, HIVE_CONFIG, HIVE_DT)

_NULLS = {"", "\\N", "null", "None"}


def _clean(value):
    """把 OpenFlights 的空值标记统一成空字符串。"""
    return "" if (value or "").strip() in _NULLS else (value or "").strip()


def _to_float(value):
    """安全解析数值字段；非法值返回 None，不让单条脏数据中断整批加载。"""
    v = _clean(value)
    try:
        return float(v)
    except ValueError:
        return None


def load_airports(path=AIRPORTS_FILE):
    """读取 OpenFlights airports.dat -> {airport_id: {...}}。

    字段顺序: ID, 名称, 城市, 国家, IATA, ICAO, 纬度, 经度, ...
    字段不足或 ID 非法的记录直接跳过（OpenFlights 存在少量不完整行）。
    """
    airports = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for row in csv.reader(f):
            if len(row) < 8:
                continue
            try:
                aid = int(row[0])
            except (ValueError, TypeError):
                continue
            airports[aid] = {
                "id": aid,
                "name": _clean(row[1]),
                "city": _clean(row[2]),
                "country": _clean(row[3]),
                "iata": _clean(row[4]),
                "icao": _clean(row[5]),
                "lat": _to_float(row[6]),
                "lon": _to_float(row[7]),
            }
    return airports


def load_routes(path=ROUTES_FILE):
    """读取 OpenFlights routes.dat -> list[(src_id, dst_id, codeshare, stops, equip)]。

    起降机场 ID 为 \\N 等非数字的记录在 int() 处即被跳过，无需二次比较。
    """
    routes = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for row in csv.reader(f):
            if len(row) < 9:
                continue
            try:
                src = int(row[3])
                dst = int(row[5])
            except (ValueError, TypeError):
                continue
            stops = int(row[7]) if row[7].strip().isdigit() else 0
            routes.append((src, dst, _clean(row[6]), stops, _clean(row[8])))
    return routes


def _load_iata_value_file(path, value_column):
    """读取「IATA -> 数值」两列型 CSV 的公共实现，跳过缺列/非法/非正值。

    文件不存在时发出告警并返回空表，避免预警功能静默恒为 0 而难以排查。
    """
    values = {}
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            for row in csv.DictReader(f):
                iata = _clean(row.get("iata_code"))
                try:
                    val = int(float(row[value_column]))
                except (ValueError, KeyError, TypeError):
                    continue
                if iata and val > 0:
                    values[iata] = val
    except FileNotFoundError:
        warnings.warn(f"真实数据文件不存在，相关指标将为空：{path}", RuntimeWarning,
                      stacklevel=3)
    return values


def load_throughput(path=THROUGHPUT_FILE):
    """读取真实吞吐量文件 -> {iata: 2023 年旅客吞吐量(人次)}。"""
    return _load_iata_value_file(path, "annual_passengers_2023")


def load_capacity(path=CAPACITY_FILE):
    """读取真实设计容量文件 -> {iata: 设计容量(人次)}。

    容量来源为各机场官方披露的近期/规划年旅客吞吐能力（中国枢纽）或 OAG 公布的
    年座位运力（全球枢纽），每个值均带来源标注，详见文件 source 列。
    """
    return _load_iata_value_file(path, "design_capacity_pax")


# ------------------------------------------------------------------ Hive 模式
def _hive_connect():
    """建立 HiveServer2 连接；依赖缺失或地址未配置时给出可执行的提示。"""
    host = (HIVE_CONFIG.get("host") or "").strip()
    if not host:
        raise RuntimeError(
            "Hive 模式未配置地址。请设置环境变量 CIVIL_AVIATION_HIVE_HOST "
            "（例如 set CIVIL_AVIATION_HIVE_HOST=192.168.1.10），并确认 HiveServer2 "
            "端口 10000 已开放；其余可选变量见 algorithm/config.py 文件头。"
        )
    try:
        from pyhive import hive  # 延迟导入：本地模式无需安装 pyhive
    except ImportError as exc:
        raise ImportError(
            "Hive 模式需要 pyhive：请在集群客户端执行 pip install pyhive thrift，"
            "或改用本地模式（CIVIL_AVIATION_SOURCE=local）。"
        ) from exc
    kwargs = {k: v for k, v in HIVE_CONFIG.items() if v not in (None, "")}
    return hive.Connection(**kwargs)


def _safe_dt(dt):
    """dt 只作为分区值拼进 SQL，先做白名单校验防止注入。"""
    dt = (dt or "").strip()
    if dt and not re.fullmatch(r"[\w\-:. ]{1,32}", dt):
        raise ValueError(f"非法 dt 分区值：{dt!r}")
    return dt


def _fetch_all(cursor, sql):
    """执行查询并按列名返回 dict 列表（去掉 Hive 返回的 table.column 前缀）。"""
    cursor.execute(sql)
    cols = [d[0].split(".")[-1] for d in (cursor.description or [])]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _as_float(v):
    try:
        return float(v) if v not in (None, "", "\\N") else None
    except (TypeError, ValueError):
        return None


def load_from_hive(hive_config=None, dt=None):
    """生产模式：从 HiveServer2 读取 ADS 层图节点/边表（已实现，可切换）。

    前置条件：
      1) 成员B 已按 data_engineering/hive_ddl/00_create_tables.sql 建表并跑完 ETL；
      2) HiveServer2 已启动；客户端 pip install pyhive thrift；
      3) 通过环境变量或 config.HIVE_CONFIG 提供 host/port/username/database/auth；
      4) 切换数据源：CIVIL_AVIATION_SOURCE=hive（默认仍为 local）。

    字段契约见《算法数据接口清单》与 docs/algorithm_api.md：
      ads_graph_node(airport_code, airport_name, city, country, province, lat, lng,
                     annual_throughput, designed_capacity, capacity_ratio, node_weight, dt)
      ads_graph_edge(from_airport_code, to_airport_code, edge_weight,
                     flight_count, route_throughput, dt)

    Returns:
        (airports, routes, edge_weights, real_tp, real_cap)
        - airports: {airport_code: {id,name,city,country,iata,icao,lat,lon}}，
          节点 ID 统一为 airport_code(IATA 三字码)，country 必须保留（含港澳台）。
        - routes:   [(from_code, to_code, "", 0, ""), ...] 与 load_routes 同构。
        - edge_weights: {(from_code, to_code): float}，覆盖频次权重。
        - real_tp / real_cap: 节点 ID -> 真实吞吐 / 设计容量（缺值不写入）。
    """
    cfg = dict(HIVE_CONFIG)
    if hive_config:
        cfg.update(hive_config)
    db = cfg.get("database") or "civil_aviation"
    conn = _hive_connect()
    cur = conn.cursor()
    try:
        partition = _safe_dt(dt if dt is not None else HIVE_DT)
        if not partition:
            rows = _fetch_all(cur, f"SELECT MAX(dt) AS dt FROM {db}.ads_graph_node")
            partition = _safe_dt(str(rows[0].get("dt") or "")) if rows else ""
        if not partition:
            raise RuntimeError(
                f"{db}.ads_graph_node 无可用 dt 分区，请先执行 Spark ETL，"
                "或用 CIVIL_AVIATION_HIVE_DT 显式指定分区。"
            )

        node_sql = (
            "SELECT airport_code, airport_name, city, country, province, lat, lng, "
            "annual_throughput, designed_capacity, capacity_ratio "
            f"FROM {db}.ads_graph_node WHERE dt = '{partition}'"
        )
        edge_sql = (
            "SELECT from_airport_code, to_airport_code, edge_weight, flight_count, "
            f"route_throughput FROM {db}.ads_graph_edge WHERE dt = '{partition}'"
        )
        node_rows = _fetch_all(cur, node_sql)
        edge_rows = _fetch_all(cur, edge_sql)
    finally:
        try:
            cur.close()
        finally:
            conn.close()

    if not node_rows:
        raise RuntimeError(
            f"{db}.ads_graph_node 在 dt={partition} 分区无数据；请检查 ETL 是否写入该分区。"
        )

    airports, real_tp, real_cap = {}, {}, {}
    for r in node_rows:
        code = _clean(r.get("airport_code")).upper()
        if not code or code == "\\N":
            continue
        airports[code] = {
            "id": code,
            "name": _clean(r.get("airport_name")),
            "city": _clean(r.get("city")) or _clean(r.get("province")),
            "country": _clean(r.get("country")),
            "province": _clean(r.get("province")),
            "iata": code,
            "icao": "",
            "lat": _as_float(r.get("lat")),
            "lon": _as_float(r.get("lng")),
        }
        tp = _as_float(r.get("annual_throughput"))
        cap = _as_float(r.get("designed_capacity"))
        if tp and tp > 0:
            real_tp[code] = int(tp)
        if cap and cap > 0:
            real_cap[code] = int(cap)

    routes, edge_weights = [], {}
    for r in edge_rows:
        s = _clean(r.get("from_airport_code")).upper()
        d = _clean(r.get("to_airport_code")).upper()
        if not s or not d or s not in airports or d not in airports or s == d:
            continue
        routes.append((s, d, "", 0, ""))
        w = _as_float(r.get("edge_weight"))
        if w and w > 0:
            edge_weights[(s, d)] = w

    return airports, routes, edge_weights, real_tp, real_cap
