# 核心算法引擎（组长独立负责）

64 号题「基于 Hive 的民航航线网络结构分析系统」的**核心算法部分**，由组长独立完成。
航线网络建模为「机场=节点、航段=边、吞吐量=权重」的加权有向图，使用 Python + NetworkX 实现。

## 模块结构
```
algorithm/
├── config.py        # 参数与路径（α/β、τ1/τ2、容量、Hive 配置；自动定位项目根）
├── loader.py        # 数据加载（本地 .dat / 真实吞吐容量 CSV / Hive 占位）
├── graph_builder.py # 构图（DiGraph，权重=航段频次）
├── metrics.py       # 中心性 / 容量耦合 / 瓶颈识别
├── vulnerability.py # 脆弱性仿真（移除 Top-K 后最大连通分量收缩）
├── warning.py       # 容量饱和预警（主）+ 高吞吐量预警（辅助参考）
├── regional.py      # 区域子图筛选（中国/港澳台）
├── report.py        # 结果导出 CSV / Excel / JSON
└── engine.py        # 编排入口 main()
```
单元测试在仓库根 `tests/test_metrics.py`（20 项）；依赖在仓库根 `requirements.txt`。

## 运行方式
```bash
# 在含 algorithm/ 与 tests/ 的仓库根目录下执行
pip install -r requirements.txt
python -m algorithm.engine
python -m unittest discover -s tests -p "test_*.py" -v
```
引擎依次：读取数据 → 构图 → 计算中心性 / 耦合 / 瓶颈 / 脆弱性 / 容量预警 →
对中国区域子图重跑一遍 → 导出 CSV 与 Excel 到项目根 `data/processed/`。
全局图与中国子图的指标结果在 `run_analysis()` 中一次算完并复用，不做重复全量计算。

## 算法功能（对应题目 10 项核心需求）
| 需求 | 实现位置 |
|---|---|
| 拓扑展示 | graph_builder（供可视化层消费） |
| 中心性排行 | metrics.compute_centrality（度/接近/介数/PageRank） |
| 容量耦合权重 | metrics.node_coupling / edge_coupling（α·利用率 + β·中心性） |
| 瓶颈航段识别 | metrics.edge_bottleneck |
| 吞吐量排序与耦合对比 | report 输出表 |
| 脆弱性评估 | vulnerability.vulnerability_simulation |
| 容量流量下钻 | regional.filter_region（按区域） |
| 报表导出 | report.write_csv / write_excel |
| 容量饱和预警 | warning.saturation_warning（τ1/τ2） |
| 区域子图筛选 | regional.filter_region |

## 与 Hive 的接口
- 算法读取项目根 `data/raw` 下的 OpenFlights 数据 + 真实吞吐/容量 CSV 作为**本地可运行样本**；
- 生产模式下，`loader.load_from_hive()` 通过 PyHive 连接 HiveServer2，读取
  ADS 层「图节点表 / 图边表」（字段契约见 `docs/algorithm_api.md`、飞书《算法数据接口清单》与 5 号《数据存储设计说明书》），
  返回与本地同构的 (airports, routes)，上层算法无需改动；
- 连接信息在 `config.HIVE_CONFIG`（【待补充】集群实际地址/账号）。

## 已确认 / 已就绪的参数
- α=0.6、β=0.4、τ1=0.75、τ2=0.90、介数抽样 k=800（2026-11-04 确认，不再改动）；
- 真实年吞吐量 `airport_throughput_2023.csv`（94 个机场）、真实设计容量 `airport_capacity_2023.csv`（20 个机场）已就位，
  容量饱和预警基于「真实吞吐 ÷ 真实设计容量」正式生效；无容量数据的机场不计入预警（不编造占位值）；
- `DEFAULT_CAPACITY` 仅作为无数据时的回退值保留，当前主流程不使用。

## 边界与兼容约定
- 空图 / 全零归一化分母 / 抽样数大于节点数 / 脏数据行 / 缺列 CSV 均做降级处理，不中断流水线；
- 预警结果为空时仍写出 CSV 表头，方便成员C 的看板直接读取；
- 区域筛选默认按 `country` 精确匹配（含港澳台），并兼容 Hive ADS 层只提供中文 `province`/`city` 的情况；
- 缺真实数据文件时 `main()` 会列出缺失路径，并提示可用 `CIVIL_AVIATION_PROJECT_ROOT` 指定项目根。

## 仍待补充
- Hive 集群连接配置（由成员B 提供地址后填入 `config.HIVE_CONFIG`），并实现 `loader.load_from_hive()` 查询逻辑；
- 其余机场的设计容量可由成员B 在 Hive ETL 阶段补全，接入方式不变。
