# -*- coding: utf-8 -*-
"""数据加载：本地原始数据(.dat)、真实吞吐/容量 CSV，以及 Hive 生产模式（占位）。"""
import csv
import warnings

from .config import (AIRPORTS_FILE, ROUTES_FILE, THROUGHPUT_FILE,
                     CAPACITY_FILE, HIVE_CONFIG)

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


def load_from_hive():
    """【待补充】生产模式：从 HiveServer2 读取 ADS 层图节点/边表。

    字段契约见《算法数据接口清单》与 5 号《数据存储设计说明书》：
      - ads_graph_node: airport_code(PK), airport_name, province, lat, lng,
                        annual_throughput, designed_capacity, capacity_ratio, node_weight
      - ads_graph_edge: from_airport_code, to_airport_code, edge_weight,
                        flight_count, route_throughput

    实现约定（便于成员B 就绪后直接接手）：
      1) 前置：pip install pyhive thrift；成员B 建好 ADS 表并启动 HiveServer2(10000)；
         在 config.HIVE_CONFIG 填入真实 host/username/database/auth。
      2) 连接：pyhive.hive.Connection(**config.HIVE_CONFIG)，查询上述两张表。
      3) 返回 (airports, routes)，须与 load_airports()/load_routes() **同构**：
         airports = {airport_code: {"id","name","city","country","iata","icao","lat","lon"}}，
         routes   = [(from_code, to_code, "", 0, ""), ...]；
         节点 ID 统一用 airport_code(IATA 三字码)，country 必须保留
         （China / Hong Kong / Macau / Taiwan），否则区域子图筛选会返回空图。
      4) 边权 edge_weight 需在构图时覆盖频次权重，可在 graph_builder.build_graph
         增加可选 edge_weights 参数；上层指标计算逻辑无需改动。
    """
    host = HIVE_CONFIG.get("host", "")
    if not host or "待补充" in host:
        raise NotImplementedError(
            "Hive 模式尚未配置：请先在 algorithm/config.py 的 HIVE_CONFIG 填入真实 "
            "HiveServer2 地址/账号，并确认成员B 已建好 ads_graph_node / ads_graph_edge；"
            "具体字段与返回结构见本函数文档。"
        )
    raise NotImplementedError(
        f"Hive 数据源 {host}:{HIVE_CONFIG.get('port')} 已配置，但查询逻辑尚未接入；"
        "请按本函数文档的 4 步约定实现后再切换生产模式。"
    )
