# 可视化（2313040115陈政桥）

本目录为系统展示层，消费组长算法产出的 ADS 结果表 / `data/processed/` 结果文件，
**不实现算法逻辑**。

## 目录结构

```
visualization/
└── web_frontend/   # 自研 Streamlit 看板（主交付，可直接运行演示）
```

## 交付物（对应分工文档第 8 节）

1. **6.数据可视化设计**（Word，1 份，已补齐）：看板页面结构、图表类型选择、
   数据源与字段契约、交互设计（区域筛选 / 节点与航段下钻 / 权重配置 / 订阅）、
   视觉规范与验收口径。
2. **可视化源码/配置**：`web_frontend/` 下的 Streamlit 看板（主交付，可直接运行）；
   Superset 为题目可选项，本项目未采用。
3. **最终展示页面**：9 个标签页，覆盖区域筛选、节点大小/颜色切换、
   边宽映射、真实经纬度拓扑布局与局部视图、双列排名对比、K 值参数区、航段反向查询、
   容量流量下钻、预警订阅与 CSV 导出。

## 快速运行

见 `web_frontend/README.md`。

## 关键口径

- 容量饱和预警（`*_saturation_warnings.csv`）是题目正式功能；
  高吞吐量繁忙度预警（`*_throughput_warnings.csv`）仅辅助参考，不能当作饱和度展示。
- 数据源路径不写死本机绝对路径；后续切 Hive 只替换取数来源，页面逻辑不变。
- 前端依赖仅 streamlit / pandas / numpy / altair；界面自适应浅色 / 深色主题，
  控件宽度参数按 Streamlit 版本自动适配，base（1.45.1）与 `streamlit_env`（1.52.1）均可直接启动。
  已用 Streamlit 官方 AppTest 在**两个环境分别**完成无浏览器冒烟测试（管理员 / 分析师登录、
  两区域数据、全部图表 spec 均通过），应用异常 0。
- 算法结果样例（项目根 `data/processed/`）已就绪，可直接演示；HiveServer2 联调环境
  就绪后仅需切换 `CIVIL_AVIATION_SOURCE=hive`，本目录代码不变。
