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

    def test_hive_placeholder_gives_actionable_error(self):
        with self.assertRaises(NotImplementedError) as ctx:
            loader.load_from_hive()
        self.assertIn("HIVE_CONFIG", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
