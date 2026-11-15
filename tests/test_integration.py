# -*- coding: utf-8 -*-
"""系统集成测试（成员D 交付，6 项）。

只依赖 Python 标准库，可在任意环境运行：
    python -m unittest discover -s tests -p "test_*.py" -v

验收口径来自《项目介绍与组员工作分配》13.1 的联调基线，以及
data/processed/ 下算法实际产出的结果文件。请勿覆盖组长的 test_metrics.py。
"""
import csv
import json
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
from algorithm import config  # noqa: E402

PROC = config.DATA_PROC_DIR

# 算法本地模式实跑基线（2026-11-05 起，2026-11-13 复核）
BASELINE = {
    "global": {"nodes": 7698, "edges": 36906, "sat": 8, "tp": 48},
    "china": {"nodes": 270, "edges": 3108, "sat": 2, "tp": 9},
}


def _rows(filename):
    path = os.path.join(PROC, filename)
    if not os.path.isfile(path):
        return None, []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


class TestResultFiles(unittest.TestCase):
    """1. 结果文件齐全且都带表头（含空结果文件）。"""

    def test_all_result_files_exist_with_header(self):
        expected = []
        for label in ("global", "china"):
            expected += [
                f"{label}_airport_metrics.csv", f"{label}_edge_bottleneck.csv",
                f"{label}_saturation_warnings.csv", f"{label}_throughput_warnings.csv",
                f"{label}_vulnerability.json",
            ]
        expected.append("civil_aviation_results.xlsx")
        missing = [f for f in expected if not os.path.isfile(os.path.join(PROC, f))]
        self.assertEqual(missing, [], f"缺少结果文件：{missing}")
        for label in ("global", "china"):
            for suffix in ("airport_metrics", "edge_bottleneck",
                           "saturation_warnings", "throughput_warnings"):
                cols, _ = _rows(f"{label}_{suffix}.csv")
                self.assertTrue(cols, f"{label}_{suffix}.csv 无表头")


class TestBaseline(unittest.TestCase):
    """2. 全局 / 中国子图规模与预警数量符合联调基线。"""

    def test_graph_scale_and_warning_counts(self):
        for label, exp in BASELINE.items():
            _, airports = _rows(f"{label}_airport_metrics.csv")
            _, edges = _rows(f"{label}_edge_bottleneck.csv")
            _, sat = _rows(f"{label}_saturation_warnings.csv")
            _, tp = _rows(f"{label}_throughput_warnings.csv")
            self.assertEqual(len(airports), exp["nodes"], f"{label} 节点数")
            self.assertEqual(len(edges), exp["edges"], f"{label} 边数")
            self.assertEqual(len(sat), exp["sat"], f"{label} 容量饱和预警数")
            self.assertEqual(len(tp), exp["tp"], f"{label} 高吞吐量预警数")


class TestWarningLogic(unittest.TestCase):
    """3. 容量饱和预警分级与真实吞吐/容量口径一致。"""

    def test_saturation_level_matches_utilization(self):
        for label in ("global", "china"):
            _, rows = _rows(f"{label}_saturation_warnings.csv")
            for r in rows:
                u = float(r["utilization"])
                lvl = int(r["level"])
                expected = 2 if u >= config.TAU2 else (1 if u >= config.TAU1 else 0)
                self.assertEqual(lvl, expected,
                                 f"{label} {r['iata']} 利用率 {u} 与等级 {lvl} 不符")
                # 利用率必须能用机场指标表里的真实数据复算出来
            _, airports = _rows(f"{label}_airport_metrics.csv")
            by_iata = {a["iata"]: a for a in airports}
            for r in rows:
                a = by_iata.get(r["iata"])
                self.assertIsNotNone(a, f"{label} 预警机场 {r['iata']} 不在指标表中")
                tp = float(a["real_throughput_2023"])
                cap = float(a["design_capacity"])
                self.assertGreater(cap, 0)
                self.assertAlmostEqual(tp / cap, float(r["utilization"]), places=5)

    def test_high_throughput_is_only_auxiliary(self):
        """高吞吐量预警与容量饱和预警是两个独立口径，不得互相代替。"""
        for label in ("global", "china"):
            _, sat = _rows(f"{label}_saturation_warnings.csv")
            _, tp = _rows(f"{label}_throughput_warnings.csv")
            sat_codes = {r["iata"] for r in sat}
            tp_codes = {r["iata"] for r in tp}
            self.assertNotEqual(sat_codes, tp_codes,
                                f"{label} 两类预警完全相同，可能存在口径混用")


class TestColumnContract(unittest.TestCase):
    """4. 机场指标表列与前端 data_loader 的字段契约一致。"""

    def test_airport_columns_match_frontend_contract(self):
        # 用 AST 静态读取列契约，避免 import 前端模块带来的 pandas 依赖
        import ast
        path = os.path.join(REPO_ROOT, "visualization", "web_frontend", "data_loader.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        contract = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "AIRPORT_COLUMNS"
                    for t in node.targets):
                contract = ast.literal_eval(node.value)
        self.assertIsNotNone(contract, "前端未定义 AIRPORT_COLUMNS 契约")
        cols, _ = _rows("global_airport_metrics.csv")
        missing = [c for c in contract if c not in cols]
        self.assertEqual(missing, [], f"指标表缺列：{missing}")


class TestHiveRoundTrip(unittest.TestCase):
    """5. Hive 结果回灌产物齐全，且列序与 5 张 ADS 结果表一致。"""

    def test_load_script_and_csv_columns(self):
        hql = os.path.join(PROC, "hive_load", "load_results.hql")
        self.assertTrue(os.path.isfile(hql), "缺少 load_results.hql")
        with open(hql, encoding="utf-8") as f:
            text = f.read()
        from algorithm.hive_writer import TABLE_SPECS
        for table, filename, columns in TABLE_SPECS:
            self.assertIn(table, text, f"HQL 缺少 {table}")
            path = os.path.join(PROC, "hive_load", filename)
            self.assertTrue(os.path.isfile(path), f"缺少 {filename}")
            # Hive LOAD DATA 的数据文件不带表头（否则表头会被当成一行数据），
            # 因此只校验列数与该表 DDL 字段数一致。
            with open(path, encoding="utf-8", newline="") as f:
                first = next(csv.reader(f), [])
            self.assertEqual(len(first), len(columns),
                             f"{filename} 列数与 {table} 的 DDL 不一致")


class TestVulnerability(unittest.TestCase):
    """6. 脆弱性仿真的 Top-K 语义：removed 必须等于 k。"""

    def test_removed_equals_k(self):
        for label in ("global", "china"):
            with open(os.path.join(PROC, f"{label}_vulnerability.json"),
                      encoding="utf-8") as f:
                v = json.load(f)
            for item in v["by_k"]:
                self.assertEqual(item["removed"], item["k"],
                                 f"{label} K={item['k']} 累计移除数不等于 K")
            drops = [i["lcc_drop_ratio"] for i in v["by_k"]]
            self.assertEqual(drops, sorted(drops), "移除节点越多，连通性下降应单调不减")


if __name__ == "__main__":
    unittest.main(verbosity=2)
