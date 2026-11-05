# -*- coding: utf-8 -*-
"""参数与路径配置（组长负责，【待补充】项需按实验/集群实际填写）。"""
import os

# ---------- 路径配置 ----------
_HERE = os.path.dirname(os.path.abspath(__file__))


def _find_project_root():
    """逐级向上定位含 data/raw/airports.dat 的目录作为项目根。

    这样无论代码仓库放在 16.项目源码/ 还是其子目录、或 clone 到任意位置，
    都能找到真实数据包；也可用环境变量 CIVIL_AVIATION_PROJECT_ROOT 显式指定。
    找不到时回退到「从 algorithm/ 往上两级」，由 engine.main 统一给出数据缺失提示。
    """
    override = os.environ.get("CIVIL_AVIATION_PROJECT_ROOT")
    if override:
        return os.path.abspath(override)
    cur = _HERE
    for _ in range(8):
        if os.path.isfile(os.path.join(cur, "data", "raw", "airports.dat")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.path.abspath(os.path.join(_HERE, "..", ".."))


PROJECT_ROOT = _find_project_root()          # 第64题-项目工件-...（项目根，含 data/raw）
DATA_RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw")
DATA_PROC_DIR = os.path.join(PROJECT_ROOT, "data", "processed")

AIRPORTS_FILE = os.path.join(DATA_RAW_DIR, "airports.dat")
ROUTES_FILE = os.path.join(DATA_RAW_DIR, "routes.dat")
AIRLINES_FILE = os.path.join(DATA_RAW_DIR, "airlines.dat")  # 辅助，可选

# 启动本地模式前必须存在的数据文件（缺失时 engine.main 给出明确提示）
REQUIRED_DATA_FILES = (AIRPORTS_FILE, ROUTES_FILE)

# ---------- 核心算法参数（2026-11-04 组内确认，不再改动） ----------
# 容量耦合权重系数
ALPHA = 0.6   # 吞吐/容量（利用率）项权重
BETA = 0.4    # 中心性/拥挤度项权重

# 容量饱和预警阈值（利用率 u = 吞吐量 / 容量）
TAU1 = 0.75   # 一级预警（偏繁忙）
TAU2 = 0.90   # 二级预警（接近饱和/严重）

# 机场设计容量（回退值：仅当某机场既无真实容量数据也无容量表时保留；
# 实际容量预警以 data/raw/airport_capacity_2023.csv 真实设计容量为准，缺失机场不计入预警）
DEFAULT_CAPACITY = 2_000_000

# ---------- 真实吞吐量数据接入（组长已拉取 2023 年真实旅客吞吐量） ----------
# True=使用真实吞吐量文件（airport_throughput_2023.csv）；False=退回航线数代理
USE_REAL_THROUGHPUT = True
THROUGHPUT_FILE = os.path.join(DATA_RAW_DIR, "airport_throughput_2023.csv")

# ---------- 真实设计容量数据接入（组长已拉取，权威公开来源，见文件 source 列） ----------
# True=使用真实设计容量文件（airport_capacity_2023.csv）计算容量饱和预警；
# False=退回航线数代理（预警将无区分度，仅用于无容量数据的演示）
USE_REAL_CAPACITY = True
CAPACITY_FILE = os.path.join(DATA_RAW_DIR, "airport_capacity_2023.csv")

# 高吞吐量(繁忙度)预警阈值（单位：人次/年；辅助参考，不替代容量饱和预警）
HIGH_TP_LEVEL1 = 40_000_000   # 一级：年旅客量 >= 4000 万（繁忙）
HIGH_TP_LEVEL2 = 60_000_000   # 二级：年旅客量 >= 6000 万（高度繁忙）

# 介数中心性：全局图用抽样近似提速；区域子图（节点数<=k）自动精确计算
BETWEENNESS_SAMPLE_K = 800

# 脆弱性仿真：累计移除排名前 K 个最重要节点（K 列表见下）
VULN_TOP_K = [3, 5, 10, 20]

# 区域子图（中国民航）：国家字段含以下关键词（含港澳台，符合中国领土完整表述）
REGION_KEYWORDS = ["China", "Hong Kong", "Macau", "Taiwan"]
# Hive ADS 层若只提供中文省市字段时的兼容别名（默认关键词下自动生效）
REGION_KEYWORDS_CN = ["中国", "香港", "澳门", "台湾"]

# ---------- Hive 生产模式连接（【待补充】集群实际配置） ----------
HIVE_CONFIG = {
    "host": "【待补充】HiveServer2 地址",
    "port": 10000,
    "username": "【待补充】",
    "database": "civil_aviation",
    "auth": "NOSASL",
}
