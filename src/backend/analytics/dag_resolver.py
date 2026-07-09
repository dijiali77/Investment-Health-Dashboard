"""
DAGResolver（拓撲排序執行引擎）

根據 MetricRegistry 的依賴圖，使用 Kahn's Algorithm 進行拓撲排序，
依序執行各指標的計算函數，確保每個節點只被計算一次。

核心流程：
1. 從 MetricRegistry 取得 DAG
2. 拓撲排序（Kahn's Algorithm）
3. 按排序依序執行各 metric function，結果快取於 context dict
4. 若偵測到循環依賴 → 拋出 CycleDetectedError
5. 最終回傳完整 MetricsBundle
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .registry import MetricRegistry


class CycleDetectedError(ValueError):
    """
    循環依賴錯誤。

    當 DAG 中存在循環依賴時拋出，附帶循環路徑資訊。
    """

    def __init__(self, cycle_nodes: List[str]):
        self.cycle_nodes = cycle_nodes
        super().__init__(
            f"偵測到循環依賴，涉及節點: {' -> '.join(cycle_nodes)}"
        )


@dataclass
class MetricsBundle:
    """
    指標計算結果捆綁包。

    包含所有已計算的指標結果，以及執行過程的元資料。

    Attributes
    ----------
    results : Dict[str, Any]
        key 為 metric_id，value 為計算結果。
    execution_order : List[str]
        執行順序（拓撲排序結果）。
    execution_time_ms : float
        總執行時間（毫秒）。
    errors : Dict[str, str]
        key 為 metric_id，value 為錯誤訊息（若有）。
    """

    results: Dict[str, Any] = field(default_factory=dict)
    execution_order: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    errors: Dict[str, str] = field(default_factory=dict)

    def get(self, metric_id: str, default: Any = None) -> Any:
        """安全地取得指定指標的計算結果。"""
        return self.results.get(metric_id, default)

    def has_errors(self) -> bool:
        """是否有任何計算錯誤。"""
        return len(self.errors) > 0

    def __contains__(self, metric_id: str) -> bool:
        return metric_id in self.results

    def __repr__(self) -> str:
        return (
            f"MetricsBundle({len(self.results)} metrics, "
            f"{len(self.errors)} errors, "
            f"{self.execution_time_ms:.1f}ms)"
        )


class DAGResolver:
    """
    DAG 拓撲排序執行引擎。

    根據 MetricRegistry 的依賴圖，使用 Kahn's Algorithm 進行拓撲排序，
    依序執行各指標的計算函數。

    Usage
    -----
    >>> resolver = DAGResolver()
    >>> bundle = resolver.resolve(registry, inputs={"nav_series": df})
    >>> bundle.get("HEALTH_SCORE")
    85.0
    """

    def __init__(self):
        self._execution_cache: Dict[str, Any] = {}

    # ── 核心方法 ──────────────────────────────────────────────────

    def resolve(
        self,
        registry: MetricRegistry,
        inputs: Optional[Dict[str, Any]] = None,
        *,
        target_metrics: Optional[List[str]] = None,
    ) -> MetricsBundle:
        """
        執行 DAG 解析與計算。

        Parameters
        ----------
        registry : MetricRegistry
            已註冊所有指標的 MetricRegistry 實例。
        inputs : Optional[Dict[str, Any]]
            外部輸入資料，會合併到 context 中供計算函數使用。
        target_metrics : Optional[List[str]]
            指定要計算的指標列表。若為 None，計算所有指標。

        Returns
        -------
        MetricsBundle
            包含所有計算結果的捆綁包。

        Raises
        ------
        CycleDetectedError
            若 DAG 中存在循環依賴。
        ValueError
            若 target_metrics 包含未註冊的指標。
        """
        import time

        start_time = time.perf_counter()

        # 1. 取得 DAG
        graph = registry.get_dependency_graph()

        # 2. 確定要計算的指標
        if target_metrics is not None:
            for mid in target_metrics:
                if mid not in graph:
                    raise ValueError(f"指標 '{mid}' 未註冊。")
            # 包含所有依賴
            all_needed = self._collect_dependencies(graph, target_metrics)
        else:
            all_needed = set(graph.keys())

        # 3. 拓撲排序
        execution_order = self._topological_sort(graph, all_needed)

        # 4. 初始化 context（含 inputs）
        context: Dict[str, Any] = {}
        if inputs:
            context.update(inputs)

        # 5. 依序執行
        errors: Dict[str, str] = {}

        for metric_id in execution_order:
            definition = registry.get(metric_id)
            if definition is None:
                continue

            try:
                result = definition.fn(context)
                context[metric_id] = result
            except Exception as e:
                errors[metric_id] = f"{type(e).__name__}: {e}"

        # 6. 只回傳 requested 的結果
        results = {
            mid: context[mid]
            for mid in all_needed
            if mid in context
        }

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return MetricsBundle(
            results=results,
            execution_order=execution_order,
            execution_time_ms=round(elapsed_ms, 2),
            errors=errors,
        )

    # ── 拓撲排序 ──────────────────────────────────────────────────

    def _topological_sort(
        self,
        graph: Dict[str, List[str]],
        nodes: Set[str],
    ) -> List[str]:
        """
        使用 Kahn's Algorithm 進行拓撲排序。

        Parameters
        ----------
        graph : Dict[str, List[str]]
            完整的依賴圖。
        nodes : Set[str]
            要排序的節點集合。

        Returns
        -------
        List[str]
            拓撲排序後的節點列表。

        Raises
        ------
        CycleDetectedError
            若偵測到循環依賴。
        """
        # 建立子圖（只包含需要的節點）
        in_degree: Dict[str, int] = {node: 0 for node in nodes}
        adjacency: Dict[str, List[str]] = {node: [] for node in nodes}

        for node in nodes:
            for dep in graph.get(node, []):
                if dep in nodes:
                    adjacency.setdefault(dep, []).append(node)
                    in_degree[node] = in_degree.get(node, 0) + 1

        # Kahn's Algorithm
        queue = deque([node for node, deg in in_degree.items() if deg == 0])
        sorted_order: List[str] = []

        while queue:
            node = queue.popleft()
            sorted_order.append(node)

            for neighbor in adjacency.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 檢查是否有循環
        if len(sorted_order) != len(nodes):
            remaining = set(nodes) - set(sorted_order)
            raise CycleDetectedError(list(remaining))

        return sorted_order

    def _collect_dependencies(
        self,
        graph: Dict[str, List[str]],
        targets: List[str],
    ) -> Set[str]:
        """
        收集目標指標及其所有傳遞依賴。

        Parameters
        ----------
        graph : Dict[str, List[str]]
            完整的依賴圖。
        targets : List[str]
            目標指標列表。

        Returns
        -------
        Set[str]
            包含目標及其所有依賴的集合。
        """
        collected: Set[str] = set()
        stack = list(targets)

        while stack:
            node = stack.pop()
            if node in collected:
                continue
            collected.add(node)
            for dep in graph.get(node, []):
                stack.append(dep)

        return collected

    # ── 快取管理 ──────────────────────────────────────────────────

    def clear_cache(self) -> None:
        """清除執行快取。"""
        self._execution_cache.clear()
