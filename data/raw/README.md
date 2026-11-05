# 原始数据集（数据源）

本目录存放民航航线网络分析所需的**原始数据集**，由 OpenFlights 公开数据拉取。

## 数据来源
- OpenFlights: https://openflights.org/data.html
- 仓库镜像: https://github.com/jpatokal/openflights/tree/master/data

## 文件清单
| 文件 | 说明 | 规模 | 拉取状态 |
|---|---|---|---|
| `airports.dat` | 机场节点表（ID/名称/城市/国家/经纬度等 14 字段） | 7,698 条 | ✅ 完整 |
| `routes.dat` | 航段（边）表（航司/起降机场ID/经停/机型，9 字段） | 67,663 条 | ✅ 完整 |
| `airlines.dat` | 航司表（辅助） | 6,162 条 | ✅ 完整 |
| `airport_throughput_2023.csv` | **真实旅客吞吐量（2023 年，按 IATA 代码对齐）** | 94 个机场 | ✅ 拉取完成 |
| `airport_capacity_2023.csv` | **真实设计容量（年旅客吞吐能力，按 IATA 代码对齐）** | 20 个机场 | ✅ 拉取完成 |

## 真实吞吐量数据 `airport_throughput_2023.csv`（2026-11-03 拉取）
> 这是让「容量饱和预警 / 高吞吐量预警」功能生效的关键**真实数据**，由组长拉取、可连同本目录一并转发给组员。

**字段**：`iata_code, airport_name_cn, country, annual_passengers_2023, source`
- `iata_code`：与 `airports.dat` 第 5 列（IATA）一致，用于算法按 IATA 对照到图节点。
- `annual_passengers_2023`：2023 年实际旅客吞吐量（人次），真实公开统计。
- `source`：数据来源标注。

**数据来源**
- 中国机场（55 个，前 55 名）：民航局《2023 年全国民用运输机场生产统计公报》整理（maigoo 榜单，单位：人次）。
- 全球枢纽（39 个，非中国）：Wikipedia / JetPunk 汇总的 2023 年全球最繁忙机场榜（含 IATA 代码）。
- 已与 `airports.dat` 交叉校验：**94 个中 91 个能在 OpenFlights 中按 IATA 匹配到对应节点**（TFU 成都天府、INC 银川河东、NTG 南通兴东 3 个因本机 OpenFlights 快照较旧未收录，属少数，不影响整体分析）。

**算法接入方式**
- 由 `algorithm/loader.py: load_throughput()` 读取，经 `metrics.build_real_throughput_map()` 按 IATA 映射到图节点。
- 受 `config.USE_REAL_THROUGHPUT` 开关控制（默认开启）。
- 驱动 `warning.throughput_warning()`「高吞吐量(繁忙度)预警」：年旅客量 ≥ 4000 万为一级、≥ 6000 万为二级。
- 运行结果见 `data/processed/{global,china}_throughput_warnings.csv`。

## 真实设计容量数据 `airport_capacity_2023.csv`（2026-11-04 拉取）
> 这是让「容量饱和预警」功能**严格基于真实容量**生效的关键数据，由组长从公开权威渠道拉取，可连同本目录一并转发给组员。

**字段**：`iata_code, airport_name, country, design_capacity_pax, basis, source`
- `design_capacity_pax`：机场设计/规划年旅客吞吐能力（人次），即容量预警的分母。
- `basis`：容量口径（本期建成保障能力 / 规划目标年 / OAG 年座位运力）。
- `source`：每一个容量值均带来源标注，便于核查。

**数据来源（权威公开渠道）**
- 中国枢纽（12 个，硬数据）：来自各地政府网站（深圳政府网 sz.gov.cn）、中国民航网（caacnews）、人民网、中国日报、中新网、杭州机场官网等披露的**扩建/规划设计年旅客吞吐能力**。例如大兴本期 7200 万、天府一期 6000 万、白云近期 1.2 亿、浦东远期 1.2 亿、首都 2019 已破亿、宝安 8000 万、长水 9500 万、咸阳 8300 万、江北 8000 万、萧山 T4 设计 5000 万、双流提质后 5000 万；虹桥 4000 万为公开资料估算，已标注「建议核实」。
- 全球枢纽（8 个，OAG 2024）：aviationa2z 汇总 OAG 公布的 2024 年各机场**座位运力**（ATL 1.255 亿、DXB 1.203 亿、HND 1.103 亿、LHR 1.032 亿、DFW 1.029 亿、DEN 0.984 亿、IST 0.966 亿、ORD 0.940 亿）。

**算法接入方式**
- 由 `algorithm/loader.py: load_capacity()` 读取，经 `metrics.build_real_capacity_map()` 按 IATA 映射到图节点。
- 受 `config.USE_REAL_CAPACITY` 开关控制（默认开启）。
- 驱动 `warning.saturation_warning()`「容量饱和预警」：`利用率 = 真实吞吐(2023) / 设计容量`，≥0.90 二级（严重）、≥0.75 一级（偏繁忙）。
- 运行结果见 `data/processed/{global,china}_saturation_warnings.csv`。

**口径与缺口透明说明（重要）**
- 利用率 = 2023 年实际吞吐 ÷ 设计（或规划/运力）容量，反映"按当前客流相对设计上限的饱和程度"；规划容量偏远期时利用率偏低属正常。
- 文件共 20 个机场具备权威容量数据（12 个中国枢纽 + 8 个全球枢纽，其中虹桥 1 个为公开资料估算并已标注「建议核实」）；与本机 OpenFlights 图节点成功对照 19 个（TFU 成都天府因快照较旧未收录）。**其余机场容量数据暂缺，算法对其利用率计 0、不计入容量预警**，保证结果真实可核查、不编造。
- 成员 B 在 Hive ETL 阶段可从机场集团年报 / ACI 数据库补全其余机场设计容量，接入方式不变（填本文件或 Hive ADS 层容量表）。

**两种预警的关系**
- 容量饱和预警（现已基于真实容量生效）：严格的"接近设计上限"判定，是系统核心功能。
- 高吞吐量(繁忙度)预警：用真实年旅客量直接分级，不需容量，作为**辅助参考**指标（≥4000 万一级、≥6000 万二级）。

## 字段要点（供算法消费）
- `airports.dat` 第 1 列 = 机场唯一 ID（与 routes 的起降机场 ID 关联）。
- `routes.dat` 第 4/6 列 = 起/降机场 ID；`\N` 表示缺失，算法已过滤。
- 国家字段用于区域子图筛选（中国含港澳台）。

## 与 Hive 的关系
- 本目录数据为**本地可运行样本**，对应 Hive ADS 层「图节点表 / 图边表」的同构来源；
- 生产环境由成员B 经 Spark SQL ETL 落地到 Hive，组长算法引擎通过
  `16.项目源码/civil-aviation-network/algorithm/loader.py: load_from_hive()` 读取
  （字段契约详见 5 号《数据存储设计说明书》、《算法数据接口清单》与仓库 `docs/algorithm_api.md`；
  该模式目前仍为占位，需成员B 提供 HiveServer2 地址后接入）。

> 注：数据拉取受代理网络影响出现过截断，已通过断点续传校验字节数补齐；
> 若需更新，重新下载并核对 Content-Length 即可。
