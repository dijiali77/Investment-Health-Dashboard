"""
Analytics Layer（分析層）

提供 Metric DAG 引擎與健康評分系統：
- MetricRegistry：指標註冊表，管理指標定義與依賴關係
- DAGResolver：拓撲排序執行引擎，確保每個節點只計算一次
- HealthScoreCalculator：投資組合健康評分算子（0~100）
"""

from .registry import MetricRegistry, MetricDefinition
from .dag_resolver import DAGResolver, MetricsBundle, CycleDetectedError
from .health_score import HealthScoreCalculator, HealthScoreResult

__all__ = [
    "MetricRegistry",
    "MetricDefinition",
    "DAGResolver",
    "MetricsBundle",
    "HealthScoreCalculator",
    "HealthScoreResult",
]
