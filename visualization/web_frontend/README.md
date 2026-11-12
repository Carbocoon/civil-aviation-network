# 可视化前端（web_frontend）

成员C 自研的可交互看板，基于 **Streamlit + Plotly + Pandas**，消费算法产出的
`data/processed/` 结果文件，不实现算法逻辑。

## 目录说明

```
web_frontend/
├── app.py            # Streamlit 主页面（拓扑/排行/对比/瓶颈/预警/脆弱性/下钻/导出）
├── data_loader.py    # 结果文件读取与容错（路径可配置，不写死本机绝对路径）
├── requirements.txt  # 前端依赖
└── subscriptions.csv # 预警订阅记录（运行后自动生成，不入库）
```

## 本地运行

1. 进入仓库根目录，建议先建虚拟环境：
```powershell
python -m venv .venv
.venv\Scripts\activate
```

2. 安装前端依赖：
```powershell
pip install -r visualization/web_frontend/requirements.txt
```

3. 准备数据（二选一）：
   - 在仓库根运行算法生成结果：`python -m algorithm.engine`（需完整 `data/raw/` 数据包）；
   - 或直接向组长索取 `data/processed/` 结果样例，放到项目根 `data/processed/`。

4. 启动看板：
```powershell
streamlit run visualization/web_frontend/app.py
```
浏览器自动打开（默认 http://localhost:8501）。

## 数据源与路径约定

- 默认从项目根 `data/processed/` 读取；若仓库位置变动，可设置环境变量
  `CIVIL_AVIATION_PROJECT_ROOT` 指向项目根目录。
- 结果文件（前缀 `global` / `china`）：
  - `{label}_airport_metrics.csv`：机场指标汇总
  - `{label}_edge_bottleneck.csv`：航段瓶颈
  - `{label}_saturation_warnings.csv`：容量饱和预警（正式功能）
  - `{label}_throughput_warnings.csv`：高吞吐量繁忙度预警（辅助参考，非饱和度）
  - `{label}_vulnerability.json`：脆弱性仿真
- 切换 Hive 数据源时，仅替换 `data_loader.py` 的取数来源，页面与图表逻辑不变。

## 功能与题目需求对照

| 题目需求 | 页面位置 |
|---|---|
| 1 航线网络拓扑展示 | 「网络拓扑」标签页 |
| 2 耦合权重口径展示 | 侧边栏 α/β、τ1/τ2 只读说明 |
| 3 机场中心性排行 | 「中心性排行」标签页 |
| 4 结构性瓶颈航段/机场识别 | 「瓶颈识别」标签页 |
| 5 吞吐量排序与耦合对比 | 「吞吐-耦合对比」标签页 |
| 6 瓶颈脆弱性评估 | 「脆弱性评估」标签页 |
| 7 容量流量下钻 | 「容量流量下钻」标签页 |
| 8 分析报表导出 | 页面底部 CSV 下载 |
| 9 容量饱和预警订阅 | 「容量饱和预警」标签页订阅表单 |
| 10 区域子图筛选 | 侧边栏 全球 / 中国（含港澳台） |

## 注意事项

- `*_saturation_warnings.csv` 是正式饱和预警；`*_throughput_warnings.csv` 仅辅助参考，
  不得在页面上当作饱和度结论展示。
- 真实数据与算法产出不入库；`subscriptions.csv` 为本地演示记录。
