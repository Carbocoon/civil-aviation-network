# 民航航线网络结构分析系统 · 代码仓库

**本目录（位于 `16.项目源码/civil-aviation-network/`）即 Git 仓库根**：把本目录初始化为 Git 仓库并推送到 GitHub，即可对个人代码做版本管理；课程交付工件（docx / xls / pptx）仍按学校模板放在项目根目录，不入库。

系统把民航航线抽象为「机场为点、航段为边、吞吐量为权」的加权有向图，实现中心性排行、瓶颈识别、脆弱性评估、容量饱和预警、区域子图筛选，并提供可视化看板。

## 技术栈
- 存储 / 计算：HDFS、Hive、Spark SQL
- 核心算法：Python + networkx（详见 `algorithm/README.md`）
- 图数据库：Neo4j（可选）
- 可视化：Superset（可选）

## 协作方式（飞书 + GitHub）
- 文档（需求、计划、纪要、手册、接口清单）统一放在 **飞书**，方便多人实时协作编辑。
- 代码与技术契约放在本 GitHub 仓库，由组长管理并负责上传。
- 两边互相链接：飞书《算法数据接口清单》↔ 仓库 `docs/algorithm_api.md`；关键决策在飞书讨论、对应任务用 GitHub Issue 跟踪，避免信息割裂。

## 目录结构（推荐，非强制）
> 以下目录组织为**推荐方案，并非严格要求**；组员可按实际技术选型调整目录与文件组织方式，只要能跑通并符合接口契约即可。

```
civil-aviation-network/         ← Git 仓库根
├── algorithm/                  # 组长：核心算法引擎（Python 包），详见其内 README
├── tests/                      # test_metrics.py 算法单测；成员D 的集成测试也放这里
├── data_engineering/           # 成员B：hive_ddl / spark_etl / neo4j_import（待填充）
├── visualization/              # 成员C：superset / web_frontend（待填充）
├── docs/                       # 技术文档（algorithm_api.md：算法接口契约）
├── requirements.txt            # Python 依赖
└── .gitignore
```

## 数据放在哪里（重要）
真实数据**不入库**，由组长以数据包形式单独提供，位于**项目根 `第64题-项目工件-.../data/raw/`**（在仓库根之外）。

- `algorithm/config.py` 会从 `algorithm/` 开始**逐级向上查找**含 `data/raw/airports.dat` 的目录作为项目根，因此仓库放在 `16.项目源码/` 下或更深一层都能自动找到数据，无需改代码。
- 若把仓库 clone 到别处，可设置环境变量 `CIVIL_AVIATION_PROJECT_ROOT` 指向项目根目录；找不到必需数据文件时引擎会直接列出缺失路径与解决办法。
- 数据包内容：`airports.dat`、`routes.dat`、`airlines.dat`、`airport_throughput_2023.csv`、`airport_capacity_2023.csv`。
- 算法输出写入项目根 `data/processed/`（预警结果即使为空也保留表头，便于看板读取）。

## 快速开始
```bash
# 在本仓库根目录下执行
pip install -r requirements.txt
python -m algorithm.engine                              # 本地模式：读 data/raw，结果写入 data/processed/
python -m unittest discover -s tests -p "test_*.py" -v   # 算法单元测试（20 项）
```

生产模式（Hive）：配置 `algorithm/config.py` 的 `HIVE_CONFIG`、成员B 建库后，由 `loader.load_from_hive()` 读取 ADS 层图节点 / 图边表。具体字段与返回结构见 `docs/algorithm_api.md` 及 `loader.load_from_hive()` 文档；**该模式目前仍为占位，需集群就绪后接入**。

## 如何贡献
1. 从 `main` 切出功能分支（如 `feature/data-pipeline`）。
2. 在功能分支开发，完成后提 PR 给组长 review，**勿直接推 `main`**。
3. PR 描述关联对应飞书文档 / GitHub Issue。
