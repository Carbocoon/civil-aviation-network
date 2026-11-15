# 测试目录

本目录包含两类自动化测试：

- `test_metrics.py`：核心算法**单元测试**（组长维护，20 项，合成小图、不依赖真实数据）。
- `test_pipeline_integration.py`：**端到端集成测试**（成员D 维护，6 项，合成小数据集跑通全链路）。

## 运行方式

在**仓库根目录**（含 `algorithm/` 与 `tests/` 的目录，即 `civil-aviation-network/`）下执行：

```bash
# 全部测试（单元 + 集成）
python -m unittest discover -s tests -v

# 只跑集成测试
python -m unittest tests.test_pipeline_integration -v

# 只跑单元测试
python -m unittest tests.test_metrics -v
```

建议先激活项目虚拟环境（`.venv\Scripts\Activate.ps1`），并已安装 `requirements.txt` 与
`visualization\web_frontend\requirements.txt` 中的依赖（networkx、pandas、openpyxl）。

## 单元测试覆盖范围（test_metrics.py）

中心性与抽样降级、耦合权重、节点/边瓶颈、两类预警分级、脆弱性 Top-K 语义、
区域筛选中英文兼容、空图与除零、脏数据加载、自环/孤立航段计数、空表头导出、Hive 占位提示。

## 集成测试覆盖范围（test_pipeline_integration.py）

与单元测试的区别：**不 mock 任何算法函数**，真实调用 `algorithm.engine.run_analysis` 流水线，
并验证可视化层 `data_loader` 能正确消费算法产出，即"算法导出契约 ↔ 看板读取契约"两端对齐。

### 合成测试数据

| 机场 | IATA | 国家 | 真实吞吐量(人次/年) | 设计容量(人次/年) | 利用率 | 预警级别 |
|---|---|---|---|---|---|---|
| 上海浦东 | SHA | China | 10,623,190 | 10,000,000 | 1.0623 | 二级（≥τ2=0.90） |
| 杭州萧山 | HGH | China | 8,234,090 | 10,000,000 | 0.8234 | 一级（τ1~τ2 之间） |
| 北京首都 | PEK | China | 5,000,000 | 10,000,000 | 0.5000 | 不预警 |
| 伦敦希思罗 | LHR | United Kingdom | 无 | 无 | 0.0000 | 不预警 |

航段 7 条（SHA↔HGH、SHA↔PEK、HGH→PEK、PEK↔LHR，均为直飞），构成 4 节点 7 边的有向图。

### 用例清单

| 用例 | 验证内容 |
|---|---|
| `test_01_pipeline_writes_all_expected_files` | 全流程产出 5 个结果文件（`{label}_airport_metrics.csv`、`{label}_edge_bottleneck.csv`、`{label}_saturation_warnings.csv`、`{label}_throughput_warnings.csv`、`{label}_vulnerability.json`）齐全 |
| `test_02_warning_levels_match_utilization_thresholds` | 利用率数值与 τ1/τ2 阈值口径正确：SHA 二级、HGH 一级、PEK 不预警；预警文件按级别降序排列 |
| `test_03_airport_rows_sorted_by_coupling_desc` | 机场指标表行数=节点数，且按耦合权重 `coupling` 降序 |
| `test_04_china_subgraph_pipeline` | 中国区域子图（含港澳台）正确筛出 3 个国内节点，并独立产出 `china_*` 结果文件 |
| `test_05_vulnerability_simulation_shape` | 脆弱性仿真覆盖 `VULN_TOP_K = [3,5,10,20]` 全部 k 值，节点全部移除后 LCC=0、下降比例=1.0 |
| `test_06_frontend_loader_consumes_algorithm_outputs` | `data_loader` 能直接读取算法产出的 CSV/JSON：列齐全、行数一致；读取不存在的文件时返回空 DataFrame 而不崩溃 |

### 设计约定

- **不污染真实数据目录**：通过 `mock.patch.object(report, "DATA_PROC_DIR", tmpdir)`
  把所有结果文件重定向到系统临时目录，测试结束自动清理，不会写入项目的 `data/processed/`。
- **不依赖 OpenFlights 全量数据**：构造 4 节点小图，5 秒内跑完，适合提交前快速回归。
- **数值与文档对齐**：合成数据的利用率（1.062319 / 0.823409）刻意与
  《用户使用手册》《测试日志》中 SHA/HGH 的口径保持一致，改动阈值或权重公式会立即失败。
- **契约回归**：任何改动 `build_airport_rows` 列名、CSV 表头或 `data_loader` 读取逻辑的
  修改，都会被 `test_06` 抓住。

### 暂不覆盖（后续补充）

- Hive 生产模式：`loader.load_from_hive()` 尚未实现（BUG-01），待 PyHive 接入后补
  "Hive ADS 表 → 同构图 → 指标一致"的集成用例。
- Streamlit 浏览器端到端（点击标签页、截图比对）：建议后续用 Playwright 单独建 `tests/e2e/`。
- 性能基准（7698 节点全图批处理耗时 ≤30s）：受机器负载影响大，放在性能测试脚本中，不纳入本套件。
