"""
MetricRegistry（指標註冊表）

管理指標定義與依賴關係，提供 DAG 圖的建構與查詢介面。

每個指標（Metric）定義包含：
- metric_id: 唯一識別碼
- description: 描述
- depends_on: 依賴的其他 metric_id 列表
- fn: 實際計算函數（Callable）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass(frozen=True)
class MetricDefinition:
    """
    指標定義（不可變）。

    Attributes
    ----------
    metric_id : str
        唯一識別碼，如 "NAV", "DAILY_RETURN", "HEALTH_SCORE"。
    description : str
        指標描述。
    depends_on : List[str]
        依賴的其他 metric_id 列表。若為空列表，表示無依賴（根節點）。
    fn : Callable
        實際計算函數。簽名為 fn(context: Dict[str, Any], **kwargs) -> Any。
        計算結果應存入 context[metric_id]。
    """

    metric_id: str
    description: str
    depends_on: List[str] = field(default_factory=list)
    fn: Callable = field(default=lambda ctx, **kw: None)


class MetricRegistry:
    """
    指標註冊表。

    管理所有可用的指標定義，提供 DAG 圖的建構與查詢。
    支援動態註冊與取消註冊。

    Usage
    -----
    >>> registry = MetricRegistry()
    >>> registry.register("NAV", "每日淨資產", [], compute_nav)
    >>> registry.register("DAILY_RETURN", "日報酬率", ["NAV"], compute_daily_return)
    >>> registry.get_dependency_graph()
    {"NAV": [], "DAILY_RETURN": ["NAV"]}
    """

    def __init__(self):
        self._metrics: Dict[str, MetricDefinition] = {}

    # ── 註冊與查詢 ────────────────────────────────────────────────

    def register(
        self,
        metric_id: str,
        description: str,
        depends_on: List[str],
        fn: Callable,
    ) -> MetricDefinition:
        """
        註冊一個指標。

        Parameters
        ----------
        metric_id : str
            唯一識別碼。
        description : str
            指標描述。
        depends_on : List[str]
            依賴的其他 metric_id 列表。
        fn : Callable
            計算函數。

        Returns
        -------
        MetricDefinition
            已註冊的指標定義。

        Raises
        ------
        ValueError
            若 metric_id 已存在，或 depends_on 包含尚未註冊的指標。
        """
        if metric_id in self._metrics:
            raise ValueError(f"指標 '{metric_id}' 已註冊。")

        # 驗證依賴存在（允許空列表）
        for dep in depends_on:
            if dep not in self._metrics:
                raise ValueError(
                    f"指標 '{metric_id}' 依賴的 '{dep}' 尚未註冊。"
                )

        definition = MetricDefinition(
            metric_id=metric_id,
            description=description,
            depends_on=list(depends_on),
            fn=fn,
        )
        self._metrics[metric_id] = definition
        return definition

    def unregister(self, metric_id: str) -> None:
        """
        取消註冊一個指標。

        Parameters
        ----------
        metric_id : str
            要取消註冊的指標 ID。

        Raises
        ------
        ValueError
            若 metric_id 不存在，或仍有其他指標依賴它。
        """
        if metric_id not in self._metrics:
            raise ValueError(f"指標 '{metric_id}' 不存在。")

        # 檢查是否有其他指標依賴此指標
        for mid, defn in self._metrics.items():
            if metric_id in defn.depends_on:
                raise ValueError(
                    f"無法取消註冊 '{metric_id}'，因為 '{mid}' 仍依賴它。"
                )

        del self._metrics[metric_id]

    def get(self, metric_id: str) -> Optional[MetricDefinition]:
        """取得指定指標的定義。"""
        return self._metrics.get(metric_id)

    def get_all_metric_ids(self) -> List[str]:
        """取得所有已註冊的指標 ID。"""
        return list(self._metrics.keys())

    def get_dependency_graph(self) -> Dict[str, List[str]]:
        """
        取得完整的依賴圖。

        Returns
        -------
        Dict[str, List[str]]
            key 為 metric_id，value 為其依賴的 metric_id 列表。
        """
        return {
            mid: list(defn.depends_on)
            for mid, defn in self._metrics.items()
        }

    def get_leaf_metrics(self) -> List[str]:
        """
        取得所有葉節點指標（不被任何其他指標依賴的指標）。

        Returns
        -------
        List[str]
            葉節點指標 ID 列表。
        """
        depended_upon: set = set()
        for defn in self._metrics.values():
            depended_upon.update(defn.depends_on)

        return [
            mid for mid in self._metrics
            if mid not in depended_upon
        ]

    def get_root_metrics(self) -> List[str]:
        """
        取得所有根節點指標（無依賴的指標）。

        Returns
        -------
        List[str]
            根節點指標 ID 列表。
        """
        return [
            mid for mid, defn in self._metrics.items()
            if not defn.depends_on
        ]

    def count(self) -> int:
        """取得已註冊的指標數量。"""
        return len(self._metrics)

    def clear(self) -> None:
        """清除所有註冊的指標。"""
        self._metrics.clear()

    def __contains__(self, metric_id: str) -> bool:
        return metric_id in self._metrics

    def __len__(self) -> int:
        return len(self._metrics)

    def __repr__(self) -> str:
        return (
            f"MetricRegistry({len(self._metrics)} metrics: "
            f"{list(self._metrics.keys())})"
        )
