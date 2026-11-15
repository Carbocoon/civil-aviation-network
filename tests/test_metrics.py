# -*- coding: utf-8 -*-
"""核心算法单元测试（不依赖真实数据集，使用合成小图）。"""
import os
import sys
import tempfile
import unittest
from unittest import mock

# 允许直接运行：将 algorithm 包加入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algorithm import (config, graph_builder, loader, metrics,  # noqa: E402
                       regional, report, vulnerability, warning)
import networkx as nx  # noqa: E402


def make_triangle():
    """A->B->C->A 的有向三角，边权重 1。"""
    G = nx.DiGraph()
    G.add_node(1, country="China", name="A", iata="AAA")
    G.add_node(2, country="China", name="B", iata="BBB")
    G.add_node(3, country="China", name="C", iata="CCC")
    G.add_edge(1, 2, weight=1)
    G.add_edge(2, 3, weight=1)
    G.add_edge(3, 1, weight=1)
    return G


class TestMetrics(unittest.TestCase):
    def test_centrality_keys(self):
        G = make_triangle()
        c = metrics.compute_centrality(G, k=None)
        for key in ["weighted_degree", "closeness", "betweenness", "pagerank"]:
            self.assertIn(key, c)
            self.assertEqual(len(c[key]), 3)

    def test_throughput_eq_weighted_degree(self):
        G = make_triangle()
        c = metrics.compute_centrality(G, k=None)
        tp = metrics.compute_throughput_proxy(G, c)
        # 每个节点出度1+入度1=2
        self.assertTrue(all(v == 2 for v in tp.values()))

    def test_node_coupling_in_range(self):
        G = make_triangle()
        c = metrics.compute_centrality(G, k=None)
        tp = metrics.compute_throughput_proxy(G, c)
        coup, util = metrics.node_coupling(G, c, tp)
        for n in G:
            self.assertGreaterEqual(coup[n], 0.0)
            self.assertGreaterEqual(util[n], 0.0)

    def test_edge_bottleneck_shape(self):
        G = make_triangle()
        c = metrics.compute_centrality(G, k=None)
        tp = metrics.compute_throughput_proxy(G, c)
        ec = metrics.edge_coupling(G, tp)
        self.assertEqual(len(ec), 3)
        nb = metrics.edge_bottleneck(G, ec, None)
        self.assertEqual(len(nb), 3)

    def test_warning_levels(self):
        G = make_triangle()
        c = metrics.compute_centrality(G, k=None)
        tp = metrics.compute_throughput_proxy(G, c)
        # 未传容量表 -> 利用率恒 0，无预警
        _, util = metrics.node_coupling(G, c, tp)
        warns = warning.saturation_warning(G, util)
        self.assertEqual(len(warns), 0)

    def test_regional_filter(self):
        G = make_triangle()
        G.add_node(4, country="United States", name="D")
        G.add_edge(4, 1, weight=1)
        sub = regional.filter_region(G, keywords=["China"])
        self.assertEqual(set(sub.nodes()), {1, 2, 3})

    # ---------------- 以下为健壮性 / 契约回归测试 ----------------
    def test_centrality_k_clamped_for_small_graph(self):
        """抽样数大于节点数时自动精确计算，不抛 networkx 的 random.sample 错误。"""
        G = make_triangle()
        c = metrics.compute_centrality(G)   # 默认 k=800 > 3
        self.assertEqual(len(c["betweenness"]), 3)

    def test_empty_graph_is_safe(self):
        G = nx.DiGraph()
        c = metrics.compute_centrality(G, k=None)
        coup, util = metrics.node_coupling(G, c, {})
        nb = metrics.node_bottleneck(G, c, coup, util)
        self.assertEqual((coup, util, nb), ({}, {}, {}))
        self.assertEqual(metrics.edge_coupling(G, {}), {})
        self.assertEqual(metrics.edge_bottleneck(G, {}, {}), {})

    def test_edge_bottleneck_zero_betweenness_no_divzero(self):
        G = nx.DiGraph()
        G.add_edge(1, 2, weight=1)
        score = metrics.edge_bottleneck(G, {(1, 2): 0.5}, {(1, 2): 0.0})
        self.assertEqual(score[(1, 2)], 0.0)

    def test_edge_bottleneck_falls_back_to_coupling(self):
        """缺边介数时按耦合权重降级评分，与文档说明一致。"""
        G = nx.DiGraph()
        G.add_edge(1, 2, weight=1)
        score = metrics.edge_bottleneck(G, {(1, 2): 0.5}, None)
        self.assertEqual(score[(1, 2)], 0.5)

    def test_real_capacity_warning_levels(self):
        G = make_triangle()
        util = {1: 0.74, 2: 0.80, 3: 0.95}
        warns = warning.saturation_warning(G, util)
        self.assertEqual([w["level"] for w in warns], [2, 1])
        self.assertEqual(warns[0]["node"], 3)

    def test_throughput_warning_skips_unknown_nodes(self):
        G = make_triangle()
        res = warning.throughput_warning(G, {1: config.HIGH_TP_LEVEL2,
                                             999: config.HIGH_TP_LEVEL2})
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["level"], 2)

    def test_iata_value_maps(self):
        G = nx.DiGraph()
        G.add_node(1, iata="PEK")
        G.add_node(2, iata="\\N")
        self.assertEqual(metrics.build_real_throughput_map(G, {"PEK": 100}), {1: 100})
        self.assertEqual(metrics.build_real_capacity_map(G, {"PEK": 200}), {1: 200})

    def test_vulnerability_topk_semantics(self):
        """每个场景的累计移除节点数应等于该场景的 k。"""
        G = nx.complete_graph(30).to_directed()
        centrality = {"betweenness": {n: float(n) for n in G}}
        res = vulnerability.vulnerability_simulation(G, centrality)
        self.assertEqual([r["removed"] for r in res["by_k"]], config.VULN_TOP_K)

    def test_vulnerability_unknown_score_key(self):
        G = make_triangle()
        with self.assertRaises(ValueError):
            vulnerability.vulnerability_simulation(G, {}, score_key="nope")

    def test_regional_filter_chinese_alias(self):
        """Hive ADS 层只给中文 province 时仍能筛出中国机场。"""
        G = nx.DiGraph()
        G.add_node(1, province="中国香港")
        G.add_node(2, country="United States")
        self.assertEqual(set(regional.filter_region(G).nodes()), {1})

    def test_graph_builder_counts_self_loops_and_orphans(self):
        airports = {1: {"id": 1}, 2: {"id": 2}}
        routes = [(1, 1, "", 0, ""), (1, 2, "", 0, ""), (1, 99, "", 0, "")]
        G, info = graph_builder.build_graph(airports, routes)
        self.assertEqual(info["self_loops_removed"], 1)
        self.assertEqual(info["skipped_orphan_routes"], 1)
        self.assertEqual(G.number_of_edges(), 1)

    def test_loader_skips_dirty_airport_rows(self):
        content = ('1,"A","City","China",PEK,ZBAA,40.1,116.6\n'
                   'bad,row\n'
                   '2,"B"\n'
                   '3,"C","City","China",\\N,\\N,\\N,\\N\n')
        with tempfile.NamedTemporaryFile("w", suffix=".dat", delete=False,
                                         encoding="utf-8", newline="") as f:
            f.write(content)
            path = f.name
        try:
            airports = loader.load_airports(path)
            self.assertEqual(set(airports), {1, 3})
            self.assertEqual(airports[3]["iata"], "")
            self.assertIsNone(airports[3]["lat"])
            self.assertEqual(airports[1]["lat"], 40.1)
        finally:
            os.unlink(path)

    def test_write_csv_keeps_header_when_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(report, "DATA_PROC_DIR", tmp):
                path = report.write_csv([], "empty.csv", fieldnames=("a", "b"))
            with open(path, encoding="utf-8-sig") as f:
                self.assertEqual(f.read().strip(), "a,b")

    def test_hive_mode_requires_host(self):
        """未配置地址时给出可执行的提示，而不是含糊的 NotImplementedError。"""
        with mock.patch.object(loader, "HIVE_CONFIG", {"host": ""}):
            with self.assertRaises(RuntimeError) as ctx:
                loader.load_from_hive()
        self.assertIn("CIVIL_AVIATION_HIVE_HOST", str(ctx.exception))

    def test_load_from_hive_maps_ads_rows(self):
        """用假 HiveServer2 游标验证 ADS 行 -> 算法同构数据的转换。"""
        node_desc = [(x,) for x in (
            "airport_code", "airport_name", "city", "country", "province",
            "lat", "lng", "annual_throughput", "designed_capacity", "capacity_ratio")]
        edge_desc = [(x,) for x in (
            "from_airport_code", "to_airport_code", "edge_weight",
            "flight_count", "route_throughput")]
        node_rows = [
            ("SHA", "上海虹桥", "Shanghai", "China", "Shanghai",
             31.19, 121.33, 42492745, 40000000, 1.062319),
            ("PEK", "北京首都", "Beijing", "China", "Beijing",
             40.08, 116.58, 52879156, None, None),
        ]
        edge_rows = [("SHA", "PEK", 12.5, 25, 0), ("PEK", "XXX", 3.0, 6, 0)]

        class FakeCursor:
            description = node_desc

            def __init__(self):
                self.sql = ""

            def execute(self, sql):
                self.sql = sql
                if "ads_graph_edge" in sql:
                    self.description = edge_desc
                    self._rows = edge_rows
                elif "MAX(dt)" in sql:
                    self.description = [("dt",)]
                    self._rows = [("2026-11-13",)]
                else:
                    self.description = node_desc
                    self._rows = node_rows

            def fetchall(self):
                return self._rows

            def close(self):
                pass

        class FakeConn:
            def __init__(self):
                self.c = FakeCursor()

            def cursor(self):
                return self.c

            def close(self):
                pass

        fake_hive = mock.MagicMock()
        fake_hive.Connection.return_value = FakeConn()
        fake_pyhive = mock.MagicMock()
        fake_pyhive.hive = fake_hive

        with mock.patch.dict(sys.modules, {"pyhive": fake_pyhive}), \
             mock.patch.object(loader, "HIVE_CONFIG", {"host": "unit-test-host"}), \
             mock.patch.object(loader, "HIVE_DT", "2026-11-13"):
            airports, routes, edge_w, real_tp, real_cap = loader.load_from_hive()

        self.assertEqual(set(airports), {"SHA", "PEK"})
        self.assertEqual(airports["SHA"]["country"], "China")   # 区域子图依赖该字段
        self.assertEqual(airports["SHA"]["iata"], "SHA")        # 节点 ID 用 IATA
        self.assertEqual(routes, [("SHA", "PEK", "", 0, "")])  # 孤立边被过滤
        self.assertEqual(edge_w, {("SHA", "PEK"): 12.5})
        self.assertEqual(real_tp["PEK"], 52879156)
        self.assertEqual(real_cap, {"SHA": 40000000})           # 缺容量不落占位值

    def test_build_graph_uses_hive_edge_weights(self):
        airports = {1: {"id": 1, "iata": "AAA"}, 2: {"id": 2, "iata": "BBB"}}
        routes = [(1, 2, "", 0, "")]
        G, _ = graph_builder.build_graph(airports, routes, direct_only=False,
                                         edge_weights={(1, 2): 7.25})
        self.assertEqual(G[1][2]["weight"], 7.25)

    def test_hive_writer_generates_load_script(self):
        from algorithm import hive_writer
        res = {
            "label": "global",
            "airport_rows": [{"airport_id": 1, "iata": "AAA", "w_degree": 10,
                              "closeness": 0.5, "betweenness": 0.1,
                              "pagerank": 0.2, "coupling": 0.6}],
            "edge_rows": [{"src_id": 1, "dst_id": 2, "bottleneck": 0.3}],
            "vuln_by_k": [{"k": 3, "removed": 3, "lcc_drop_ratio": 0.05}],
            "warnings_rows": [{"airport_id": 1, "iata": "AAA",
                               "utilization": 1.06, "level": 2}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            out, hql, counts = hive_writer.write_load_script(res, dt="2026-11-13",
                                                            out_dir=tmp)
            with open(hql, encoding="utf-8") as f:
                text = f.read()
            self.assertIn("LOAD DATA LOCAL INPATH 'centrality_result.csv'", text)
            self.assertIn("PARTITION (dt='2026-11-13')", text)
            self.assertEqual(counts["ads_saturation_warning"], 1)
            self.assertTrue(os.path.isfile(os.path.join(out, "bottleneck_result.csv")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
