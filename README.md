# 民航航线网络结构分析系统

**本目录（位于 `16.项目源码/civil-aviation-network/`）即 Git 仓库根**：把本目录初始化为 Git 仓库并推送到 GitHub，即可对个人代码做版本管理；课程交付工件（docx / xls / pptx）仍按学校模板放在项目根目录，不入库。

系统把民航航线抽象为「机场为点、航段为边、吞吐量为权」的加权有向图，实现中心性排行、瓶颈识别、脆弱性评估、容量饱和预警、区域子图筛选，并提供可视化看板。

## 技术栈
- 存储 / 计算：HDFS、Hive、Spark SQL
- 核心算法：Python + networkx（详见 `algorithm/README.md`）
- 图数据库：Neo4j（可选）
- 可视化：Streamlit（主交付）；Superset 为题目可选项，本项目未采用

## 协作方式（飞书 + GitHub）
- 文档（需求、计划、纪要、手册、接口清单）统一放在 **飞书**，方便多人实时协作编辑。
- 代码与技术契约放在本 GitHub 仓库，由组长管理并负责上传。
- 两边互相链接：飞书《算法数据接口清单》↔ 仓库 `docs/algorithm_api.md`；关键决策在飞书讨论、对应任务用 GitHub Issue 跟踪，避免信息割裂。

## 目录结构
```
civil-aviation-network/         ← Git 仓库根
├── algorithm/                  # 组长：核心算法引擎（含 Hive 读取与结果回灌）
├── data_engineering/           # 成员B：hive_ddl / spark_etl / ETL 执行记录
├── visualization/              # 成员C：web_frontend（Streamlit 看板，主交付）
├── tests/                      # 组长算法单测 23 项 + 成员D 集成测试 7 项
├── docs/                       # 技术文档（algorithm_api.md：算法接口契约）
├── data/raw/                   # 数据说明与吞吐/容量字典（真实 .dat 不入库）
├── requirements.txt            # 算法依赖
└── .gitignore
```

## 数据放在哪里（重要）
真实数据**不入库**，由组长以数据包形式单独提供，位于**项目根 `data/raw/`**（在仓库根之外）。

- `algorithm/config.py` 会从 `algorithm/` 开始**逐级向上查找**含 `data/raw/airports.dat` 的目录作为项目根，因此仓库放在 `16.项目源码/` 下或更深一层都能自动找到数据，无需改代码。
- 若把仓库 clone 到别处，可设置环境变量 `CIVIL_AVIATION_PROJECT_ROOT` 指向项目根目录；找不到必需数据文件时引擎会直接列出缺失路径与解决办法。
- 数据包内容：`airports.dat`、`routes.dat`、`airlines.dat`、`airport_throughput_2023.csv`、`airport_capacity_2023.csv`。
- 算法输出写入项目根 `data/processed/`（预警结果即使为空也保留表头，便于看板读取）。

## 快速开始
```bash
# 在本仓库根目录下执行
pip install -r requirements.txt
python -m algorithm.engine                              # 本地模式：读项目根 data/raw，结果写入 data/processed/
python -m unittest discover -s tests -p "test_*.py" -v   # 自动化测试（30 项：23 单测 + 7 集成）

# Streamlit 看板（base / streamlit_env 均可，自动适配 Streamlit 1.45 与 1.52+）
streamlit run visualization/web_frontend/app.py --server.port 8599
```

**生产模式（Hive，已实现，待集群联调）**：设置环境变量即可切换，不需要改代码。
```bash
export CIVIL_AVIATION_SOURCE=hive
export CIVIL_AVIATION_HIVE_HOST=<HiveServer2 地址>
export CIVIL_AVIATION_HIVE_DB=civil_aviation
python -m algorithm.engine
```
引擎通过 `loader.load_from_hive()` 读取 ADS 层 `ads_graph_node` / `ads_graph_edge`，用 ADS 的 `edge_weight` 覆盖本地频次权重；计算结束后 `hive_writer.py` 在 `data/processed/hive_load/` 生成 5 张结果表 CSV 与 `load_results.hql`，在 Hive 端执行即可回灌。字段契约与联调清单见 `docs/algorithm_api.md` 和 5 号《数据存储设计说明书》。当前只缺集群地址/账号，本机尚未做真实联调。

## 如何贡献
1. 从 `main` 切出功能分支（如 `feature/data-pipeline`）。
2. 在功能分支开发，完成后提 PR 给组长 review，**勿直接推 `main`**。
3. PR 描述关联对应飞书文档 / GitHub Issue。
