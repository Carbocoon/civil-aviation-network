# -*- coding: utf-8 -*-
"""端到端集成测试：合成小数据集跑通 构图 -> 全套指标 -> 结果导出 -> 看板读取 全链路。

与 test_metrics.py（纯单元测试）的区别：
- 这里不 mock 任何算法函数，真实调用 algorithm.engine.run_analysis 流水线；
- 仅把结果输出目录（report.DATA_PROC_DIR）重定向到临时目录，不污染项目 data/processed；
- 同时验证可视化层 data_loader 能正确消费算法导出的 CSV/JSON，
  即“算法产出契约”与“看板读取契约”两端对齐。

运行方式（仓库根目录）：
    python -m unittest tests.test_pipeline_integration -v
"""
import os
import sys
import csv
import shutil
import tempfile
import importlib.util
import unittest
from unittest import mock

# 允许直接运行：将项目根目录加入 sys.path
PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ_ROOT)

from algorithm import config, graph_builder, metrics, regional, report, engine  # noqa: E402


# ---------------------------------------------------------------- 合成测试数据
# 4 个机场：3 个中国机场（SHA/HGH/PEK）+ 1 个英国机场（LHR，无吞吐量/容量数据）
AIRPORTS = {
    1: {"id": 1, "name": "上海浦东", "city": "上海", "country": "China",
        "iata": "SHA", "icao": "ZSPD", "lat": 31.1443, "lon": 121.8083},
    2: {"id": 2, "name": "杭州萧山", "city": "杭州", "country": "China",
        "iata": "HGH", "icao": "ZSHC", "lat": 30.2295, "lon": 120.4344},
    3: {"id": 3, "name": "北京首都", "city": "北京", "country": "China",
        "iata": "PEK", "icao": "ZBAA", "lat": 40.0801, "lon": 116.5846},
    4: {"id": 4, "name": "伦敦希思罗", "city": "London", "country": "United Kingdom",
        "iata": "LHR", "icao": "EGLL", "lat": 51.4700, "lon": -0.4543},
}
# 7 条有向航段（src, dst, codeshare, stops, equip）
ROUTES = [
    (1, 2, "", 0, ""), (2, 1, "", 0, ""),
    (1, 3, "", 0, ""), (3, 1, "", 0, ""),
    (2, 3, "", 0, ""),
    (3, 4, "", 0, ""), (4, 3, "", 0, ""),
]
# IATA -> 2023 真实吞吐量 / 设计容量（人次/年）
# SHA: 10,623,190 / 10,000,000 = 1.062319（二级预警）
# HGH:  8,234,090 / 10,000,000 = 0.823409（一级预警）
# PEK:  5,000,000 / 10,000,000 = 0.500000（不预警）
TP_IATA = {"SHA": 10_623_190, "HGH": 8_234_090, "PEK": 5_000_000}
CAP_IATA = {"SHA": 10_000_000, "HGH": 10_000_000, "PEK": 10_000_000}


class TestPipelineIntegration(unittest.TestCase):
    """全链路集成测试基类：临时目录承接所有输出文件。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="carnsa_it_")
        self._proc_patch = mock.patch.object(report, "DATA_PROC_DIR", self._tmp)
        self._proc_patch.start()
        self.addCleanup(self._proc_patch.stop)
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)

    def build_global(self):
        """构图 + 接入真实吞吐/容量映射，返回 (G, real_tp, real_cap)。"""
        G, info = graph_builder.build_graph(AIRPORTS, ROUTES)
        self.assertEqual(info["nodes"], 4)
        self.assertEqual(info["edges"], 7)
        real_tp = metrics.build_real_throughput_map(G, TP_IATA)
        real_cap = metrics.build_real_capacity_map(G, CAP_IATA)
        return G, real_tp, real_cap

    def path(self, name):
        return os.path.join(self._tmp, name)

    # ------------------------------------------------------------ 用例
    def test_01_pipeline_writes_all_expected_files(self):
        """全流程跑通后应产出 5 个结果文件（2 个 CSV + 预警 CSV×2 + 脆弱性 JSON）。"""
        G, rt, rc = self.build_global()
        res = engine.run_analysis(G, label="global", real_tp=rt, real_cap=rc)

        self.assertEqual(res["n_nodes"], 4)
        self.assertEqual(res["n_edges"], 7)
        for fname in ("global_airport_metrics.csv", "global_edge_bottleneck.csv",
                      "global_saturation_warnings.csv",
                      "global_throughput_warnings.csv",
                      "global_vulnerability.json"):
            self.assertTrue(os.path.isfile(self.path(fname)), f"缺少结果文件 {fname}")

    def test_02_warning_levels_match_utilization_thresholds(self):
        """SHA 利用率 1.0623≥τ2=0.90 应为二级；HGH 0.8234 在 τ1~τ2 间应为一级；PEK 不预警。"""
        G, rt, rc = self.build_global()
        res = engine.run_analysis(G, label="global", real_tp=rt, real_cap=rc)

        self.assertEqual(res["n_warnings"], 2)
        rows = res["airport_rows"]
        by_iata = {r["iata"]: r for r in rows}
        self.assertAlmostEqual(by_iata["SHA"]["utilization"], 1.062319, places=5)
        self.assertAlmostEqual(by_iata["HGH"]["utilization"], 0.823409, places=5)
        self.assertAlmostEqual(by_iata["PEK"]["utilization"], 0.5, places=5)
        self.assertEqual(by_iata["LHR"]["utilization"], 0.0)
        self.assertEqual(by_iata["LHR"]["design_capacity"], "")

        # 预警文件按级别降序：先二级 SHA，再一级 HGH
        with open(self.path("global_saturation_warnings.csv"), encoding="utf-8-sig") as f:
            warns = list(csv.DictReader(f))
        self.assertEqual([w["iata"] for w in warns], ["SHA", "HGH"])
        self.assertEqual([int(w["level"]) for w in warns], [2, 1])
        self.assertAlmostEqual(float(warns[0]["utilization"]), 1.062319, places=5)

    def test_03_airport_rows_sorted_by_coupling_desc(self):
        """机场指标表必须按耦合权重降序，且行数等于节点数。"""
        G, rt, rc = self.build_global()
        res = engine.run_analysis(G, label="global", real_tp=rt, real_cap=rc)
        rows = res["airport_rows"]
        self.assertEqual(len(rows), 4)
        couplings = [r["coupling"] for r in rows]
        self.assertEqual(couplings, sorted(couplings, reverse=True))

    def test_04_china_subgraph_pipeline(self):
        """中国子图（含港澳台）应筛出 SHA/HGH/PEK 三个节点，并独立产出 china_* 文件。"""
        G, _, _ = self.build_global()
        Gc = regional.filter_region(G)
        self.assertEqual(set(Gc.nodes()), {1, 2, 3})

        rt_c = metrics.build_real_throughput_map(Gc, TP_IATA)
        rc_c = metrics.build_real_capacity_map(Gc, CAP_IATA)
        res = engine.run_analysis(Gc, label="china", real_tp=rt_c, real_cap=rc_c)

        self.assertEqual(res["n_nodes"], 3)
        self.assertEqual(res["n_warnings"], 2)
        for fname in ("china_airport_metrics.csv", "china_saturation_warnings.csv",
                      "china_vulnerability.json"):
            self.assertTrue(os.path.isfile(self.path(fname)), f"缺少结果文件 {fname}")

    def test_05_vulnerability_simulation_shape(self):
        """脆弱性仿真应覆盖 VULN_TOP_K 全部 k 值；4 个节点全部移除后 LCC=0。"""
        G, rt, rc = self.build_global()
        res = engine.run_analysis(G, label="global", real_tp=rt, real_cap=rc)
        by_k = res["vuln_by_k"]
        self.assertEqual([r["k"] for r in by_k], list(config.VULN_TOP_K))
        self.assertEqual(res["vuln_base_lcc"], 4)
        # k=20 时 4 个节点全部被移除
        self.assertEqual(by_k[-1]["lcc"], 0)
        self.assertAlmostEqual(by_k[-1]["lcc_drop_ratio"], 1.0, places=3)

    def test_06_frontend_loader_consumes_algorithm_outputs(self):
        """可视化层 data_loader 应能直接读取算法产出的 CSV/JSON，列齐全、行数一致。"""
        G, rt, rc = self.build_global()
        engine.run_analysis(G, label="global", real_tp=rt, real_cap=rc)

        # 动态加载 data_loader.py（visualization 目录不是 Python 包）
        dl_path = os.path.join(PROJ_ROOT, "visualization", "web_frontend", "data_loader.py")
        spec = importlib.util.spec_from_file_location("data_loader", dl_path)
        dl = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dl)
        dl.PROC_DIR = self._tmp  # 重定向到本测试的输出目录

        df, _ = dl.load_airport_metrics("global")
        self.assertEqual(len(df), 4)
        for col in ("iata", "utilization", "coupling", "bottleneck", "pagerank"):
            self.assertIn(col, df.columns)

        warns, _ = dl.load_saturation_warnings("global")
        self.assertEqual(len(warns), 2)

        vuln, _ = dl.load_vulnerability("global")
        self.assertEqual(vuln["base_lcc"], 4)
        self.assertEqual([r["k"] for r in vuln["by_k"]], list(config.VULN_TOP_K))

        # 本用例未写 china 文件 -> 看板读缺失文件应得到空 DataFrame 而不是报错
        empty, _ = dl.load_saturation_warnings("china")
        self.assertTrue(empty.empty)


if __name__ == "__main__":
    unittest.main(verbosity=2)
