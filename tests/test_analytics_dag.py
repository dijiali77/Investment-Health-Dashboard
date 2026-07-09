"""
Analytics Layer 測試

測試範圍：
1. MetricRegistry 指標註冊表
2. DAGResolver 拓撲排序執行引擎
3. HealthScoreCalculator 健康評分算子
4. DashboardService DAG 整合（health_score 回傳）
"""

from datetime import date
from typing import Any, Dict, List

import pandas as pd
import pytest

from src.backend.analytics import (
    MetricRegistry,
    MetricDefinition,
    DAGResolver,
    MetricsBundle,
    CycleDetectedError,
    HealthScoreCalculator,
    HealthScoreResult,
)
from src.backend.api.dashboard_service import DashboardService
from src.backend.ledger.domain_models import (
    SecurityTradeEvent, EventType, TradeCategory, Market,
)


# =========================================================================
# 輔助函數
# =========================================================================


def _make_buy_event(
    event_id: str, stock_id: str, event_date: date,
    quantity: int, price: float, fee: float = 0.0,
) -> SecurityTradeEvent:
    return SecurityTradeEvent(
        event_id=event_id,
        event_date=event_date,
        sequence_in_day=1,
        event_type=EventType.SECURITY_BUY,
        cash_impact=-quantity * price - fee,
        source_ref=f"test:{event_id}",
        stock_id=stock_id,
        stock_name=f"Stock-{stock_id}",
        quantity=quantity,
        price=price,
        fee=fee,
        tax=0.0,
        trade_category=TradeCategory.BOARD_LOT,
        market=Market.TWSE,
        settlement_date=event_date,
    )


def _make_market_data(
    stock_id: str, dates: list, prices: list,
) -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(dates),
        "adj_close": prices,
    })


# =========================================================================
# 1. MetricRegistry 測試
# =========================================================================


class TestMetricRegistry:
    """MetricRegistry 指標註冊表測試。"""

    def test_register_and_get(self):
        """註冊指標後應可正確取得。"""
        registry = MetricRegistry()
        fn = lambda ctx: 42
        defn = registry.register("TEST", "測試指標", [], fn)

        assert defn.metric_id == "TEST"
        assert defn.description == "測試指標"
        assert defn.depends_on == []
        assert defn.fn is fn

        retrieved = registry.get("TEST")
        assert retrieved is not None
        assert retrieved.metric_id == "TEST"

    def test_register_duplicate_raises(self):
        """重複註冊應拋出 ValueError。"""
        registry = MetricRegistry()
        registry.register("A", "指標 A", [], lambda ctx: 1)
        with pytest.raises(ValueError, match="已註冊"):
            registry.register("A", "重複", [], lambda ctx: 2)

    def test_register_missing_dependency_raises(self):
        """依賴尚未註冊的指標應拋出 ValueError。"""
        registry = MetricRegistry()
        with pytest.raises(ValueError, match="尚未註冊"):
            registry.register("B", "指標 B", ["A"], lambda ctx: 1)

    def test_register_with_existing_dependency(self):
        """依賴已註冊的指標應成功。"""
        registry = MetricRegistry()
        registry.register("A", "根節點", [], lambda ctx: 1)
        defn = registry.register("B", "依賴 A", ["A"], lambda ctx: 2)
        assert defn.depends_on == ["A"]

    def test_unregister(self):
        """取消註冊應移除指標。"""
        registry = MetricRegistry()
        registry.register("A", "指標 A", [], lambda ctx: 1)
        assert "A" in registry
        registry.unregister("A")
        assert "A" not in registry

    def test_unregister_nonexistent_raises(self):
        """取消註冊不存在的指標應拋出 ValueError。"""
        registry = MetricRegistry()
        with pytest.raises(ValueError, match="不存在"):
            registry.unregister("NONEXISTENT")

    def test_unregister_with_dependents_raises(self):
        """取消註冊仍有依賴者的指標應拋出 ValueError。"""
        registry = MetricRegistry()
        registry.register("A", "根節點", [], lambda ctx: 1)
        registry.register("B", "依賴 A", ["A"], lambda ctx: 2)
        with pytest.raises(ValueError, match="仍依賴"):
            registry.unregister("A")

    def test_get_all_metric_ids(self):
        """get_all_metric_ids 應回傳所有 ID。"""
        registry = MetricRegistry()
        registry.register("A", "", [], lambda ctx: 1)
        registry.register("B", "", [], lambda ctx: 2)
        registry.register("C", "", ["A"], lambda ctx: 3)
        ids = registry.get_all_metric_ids()
        assert set(ids) == {"A", "B", "C"}

    def test_get_dependency_graph(self):
        """get_dependency_graph 應回傳正確的依賴圖。"""
        registry = MetricRegistry()
        registry.register("A", "", [], lambda ctx: 1)
        registry.register("B", "", ["A"], lambda ctx: 2)
        registry.register("C", "", ["A", "B"], lambda ctx: 3)
        graph = registry.get_dependency_graph()
        assert graph == {"A": [], "B": ["A"], "C": ["A", "B"]}

    def test_get_root_metrics(self):
        """get_root_metrics 應回傳無依賴的指標。"""
        registry = MetricRegistry()
        registry.register("A", "", [], lambda ctx: 1)
        registry.register("B", "", [], lambda ctx: 2)
        registry.register("C", "", ["A"], lambda ctx: 3)
        roots = registry.get_root_metrics()
        assert set(roots) == {"A", "B"}

    def test_get_leaf_metrics(self):
        """get_leaf_metrics 應回傳不被依賴的指標。"""
        registry = MetricRegistry()
        registry.register("A", "", [], lambda ctx: 1)
        registry.register("B", "", ["A"], lambda ctx: 2)
        registry.register("C", "", ["A"], lambda ctx: 3)
        leaves = registry.get_leaf_metrics()
        assert set(leaves) == {"B", "C"}

    def test_count(self):
        """count 應回傳正確數量。"""
        registry = MetricRegistry()
        assert registry.count() == 0
        registry.register("A", "", [], lambda ctx: 1)
        assert registry.count() == 1
        registry.register("B", "", [], lambda ctx: 2)
        assert registry.count() == 2

    def test_clear(self):
        """clear 應清除所有指標。"""
        registry = MetricRegistry()
        registry.register("A", "", [], lambda ctx: 1)
        registry.register("B", "", [], lambda ctx: 2)
        assert registry.count() == 2
        registry.clear()
        assert registry.count() == 0

    def test_contains(self):
        """__contains__ 應正確判斷。"""
        registry = MetricRegistry()
        registry.register("A", "", [], lambda ctx: 1)
        assert "A" in registry
        assert "B" not in registry


# =========================================================================
# 2. DAGResolver 測試
# =========================================================================


class TestDAGResolver:
    """DAGResolver 拓撲排序執行引擎測試。"""

    def test_simple_chain(self):
        """簡單鏈狀依賴應正確執行。"""
        registry = MetricRegistry()
        registry.register("A", "", [], lambda ctx: 10)
        registry.register("B", "", ["A"], lambda ctx: ctx["A"] * 2)
        registry.register("C", "", ["B"], lambda ctx: ctx["B"] + 5)

        resolver = DAGResolver()
        bundle = resolver.resolve(registry)

        assert bundle.get("A") == 10
        assert bundle.get("B") == 20
        assert bundle.get("C") == 25
        assert bundle.execution_order == ["A", "B", "C"]

    def test_diamond_dependency(self):
        """鑽石型依賴（多個節點依賴同一節點）應正確計算。"""
        registry = MetricRegistry()

        registry.register("A", "", [], lambda ctx: 1)
        registry.register("B", "", ["A"], lambda ctx: ctx["A"] + 1)
        registry.register("C", "", ["A"], lambda ctx: ctx["A"] + 2)
        registry.register("D", "", ["B", "C"], lambda ctx: ctx["B"] + ctx["C"])

        resolver = DAGResolver()
        bundle = resolver.resolve(registry)

        assert bundle.get("A") == 1
        assert bundle.get("B") == 2
        assert bundle.get("C") == 3
        assert bundle.get("D") == 5

    def test_cycle_detection(self):
        """循環依賴應拋出 CycleDetectedError。"""
        registry = MetricRegistry()
        registry.register("A", "", [], lambda ctx: 1)
        registry.register("B", "", ["A"], lambda ctx: 2)
        # 手動修改依賴圖，製造循環
        registry._metrics["A"] = registry._metrics["A"].__class__(
            metric_id="A", description="", depends_on=["B"],
            fn=registry._metrics["A"].fn,
        )

        resolver = DAGResolver()
        with pytest.raises(CycleDetectedError, match="循環依賴"):
            resolver.resolve(registry)

    def test_self_cycle(self):
        """自我循環依賴應拋出 CycleDetectedError。"""
        registry = MetricRegistry()
        registry.register("A", "", [], lambda ctx: 1)
        # 手動修改依賴圖，製造自我循環
        registry._metrics["A"] = registry._metrics["A"].__class__(
            metric_id="A", description="", depends_on=["A"],
            fn=registry._metrics["A"].fn,
        )

        resolver = DAGResolver()
        with pytest.raises(CycleDetectedError, match="循環依賴"):
            resolver.resolve(registry)

    def test_target_metrics(self):
        """指定 target_metrics 應只計算需要的指標。"""
        registry = MetricRegistry()
        registry.register("A", "", [], lambda ctx: 10)
        registry.register("B", "", ["A"], lambda ctx: ctx["A"] * 2)
        registry.register("C", "", ["B"], lambda ctx: ctx["B"] + 5)

        resolver = DAGResolver()
        bundle = resolver.resolve(registry, target_metrics=["B"])

        assert "A" in bundle  # 依賴應自動包含
        assert "B" in bundle
        assert "C" not in bundle  # 不需要的指標不應計算

    def test_target_metrics_unregistered(self):
        """指定未註冊的 target_metrics 應拋出 ValueError。"""
        registry = MetricRegistry()
        registry.register("A", "", [], lambda ctx: 1)

        resolver = DAGResolver()
        with pytest.raises(ValueError, match="未註冊"):
            resolver.resolve(registry, target_metrics=["NONEXISTENT"])

    def test_inputs_passed_to_context(self):
        """外部 inputs 應傳遞到 context 中。"""
        registry = MetricRegistry()
        registry.register("SUM", "", [], lambda ctx: ctx["x"] + ctx["y"])

        resolver = DAGResolver()
        bundle = resolver.resolve(registry, inputs={"x": 10, "y": 20})

        assert bundle.get("SUM") == 30

    def test_execution_error_handling(self):
        """計算函數拋出異常時應記錄錯誤而非中斷。"""
        registry = MetricRegistry()
        registry.register("A", "", [], lambda ctx: 1)
        registry.register("B", "", ["A"], lambda ctx: 1 / 0)  # 除以零
        registry.register("C", "", ["B"], lambda ctx: ctx["B"] + 1)

        resolver = DAGResolver()
        bundle = resolver.resolve(registry)

        assert bundle.get("A") == 1
        assert bundle.has_errors()
        assert "B" in bundle.errors
        assert "ZeroDivisionError" in bundle.errors["B"]

    def test_execution_order(self):
        """執行順序應符合拓撲排序。"""
        registry = MetricRegistry()
        registry.register("A", "", [], lambda ctx: 1)
        registry.register("B", "", ["A"], lambda ctx: 2)
        registry.register("C", "", ["A"], lambda ctx: 3)
        registry.register("D", "", ["B", "C"], lambda ctx: 4)

        resolver = DAGResolver()
        bundle = resolver.resolve(registry)

        order = bundle.execution_order
        # A 必須在 B, C 之前，B, C 必須在 D 之前
        assert order.index("A") < order.index("B")
        assert order.index("A") < order.index("C")
        assert order.index("B") < order.index("D")
        assert order.index("C") < order.index("D")

    def test_execution_time_measured(self):
        """執行時間應被測量。"""
        registry = MetricRegistry()
        registry.register("A", "", [], lambda ctx: 1)

        resolver = DAGResolver()
        bundle = resolver.resolve(registry)

        assert bundle.execution_time_ms > 0

    def test_empty_registry(self):
        """空註冊表應回傳空結果。"""
        registry = MetricRegistry()
        resolver = DAGResolver()
        bundle = resolver.resolve(registry)

        assert len(bundle.results) == 0
        assert len(bundle.execution_order) == 0


# =========================================================================
# 3. HealthScoreCalculator 測試
# =========================================================================


class TestHealthScoreCalculator:
    """HealthScoreCalculator 健康評分算子測試。"""

    def test_perfect_score(self):
        """理想狀態應接近滿分。"""
        calc = HealthScoreCalculator()
        result = calc.calculate(
            positions={
                "2330": {"weight_pct": 25.0},
                "2317": {"weight_pct": 25.0},
                "2454": {"weight_pct": 25.0},
                "2308": {"weight_pct": 25.0},
            },
            cash_ratio=0.15,
            turnover_rate=0.3,
            total_return_pct=12.0,
            num_stocks=4,
            trade_count=4,
            total_trades=8,
            volatility_pct=12.0,
            max_drawdown_pct=8.0,
            sharpe_ratio=1.5,
        )
        # 理想狀態應 >= 90 分
        assert result.total_score >= 90.0
        assert result.total_score <= 100.0

    def test_extreme_concentration(self):
        """極端集中（單一持股 100%）應大幅扣分。"""
        calc = HealthScoreCalculator()
        result = calc.calculate(
            positions={"2330": {"weight_pct": 100.0}},
            cash_ratio=0.15,
            turnover_rate=0.3,
            total_return_pct=5.0,
            num_stocks=1,
            trade_count=1,
            total_trades=2,
        )
        # 集中度扣分 + 多元化扣分
        assert result.total_score < 80.0
        assert result.breakdown.get("concentration_risk", 0) < 20.0
        assert result.breakdown.get("diversification", 0) < 5.0

        # 應有集中度相關的扣分原因
        deductions_con = [
            d for d in result.deductions
            if d["dimension"] == "concentration_risk"
        ]
        assert len(deductions_con) > 0

    def test_zero_cash(self):
        """現金歸零應大幅扣分。"""
        calc = HealthScoreCalculator()
        result = calc.calculate(
            positions={
                "2330": {"weight_pct": 50.0},
                "2317": {"weight_pct": 50.0},
            },
            cash_ratio=0.0,
            turnover_rate=0.3,
            total_return_pct=5.0,
            num_stocks=2,
            trade_count=2,
            total_trades=4,
        )
        # 現金歸零應扣 10 分
        assert result.breakdown.get("cash_reserve", 20) < 20.0
        deductions_cash = [
            d for d in result.deductions
            if d["dimension"] == "cash_reserve"
        ]
        assert len(deductions_cash) > 0

    def test_excessive_turnover(self):
        """極度頻繁交易應大幅扣分。"""
        calc = HealthScoreCalculator()
        result = calc.calculate(
            positions={
                "2330": {"weight_pct": 50.0},
                "2317": {"weight_pct": 50.0},
            },
            cash_ratio=0.15,
            turnover_rate=5.0,
            total_return_pct=5.0,
            num_stocks=2,
            trade_count=2,
            total_trades=20,
        )
        # 週轉率過高應扣分
        assert result.breakdown.get("turnover", 15) < 15.0
        deductions_turn = [
            d for d in result.deductions
            if d["dimension"] == "turnover"
        ]
        assert len(deductions_turn) > 0

    def test_severe_loss(self):
        """嚴重虧損應得 0 分績效分。"""
        calc = HealthScoreCalculator()
        result = calc.calculate(
            positions={
                "2330": {"weight_pct": 50.0},
                "2317": {"weight_pct": 50.0},
            },
            cash_ratio=0.15,
            turnover_rate=0.3,
            total_return_pct=-15.0,
            num_stocks=2,
            trade_count=2,
            total_trades=4,
        )
        # 績效分應為 0
        assert result.breakdown.get("performance", 15) == 0.0

    def test_single_stock_penalty(self):
        """僅持有單一股票應有額外扣分。"""
        calc = HealthScoreCalculator()
        result = calc.calculate(
            positions={"2330": {"weight_pct": 100.0}},
            cash_ratio=0.15,
            turnover_rate=0.3,
            total_return_pct=5.0,
            num_stocks=1,
            trade_count=1,
            total_trades=2,
        )
        # 多元化分應很低
        assert result.breakdown.get("diversification", 5) < 5.0

    def test_high_volatility_penalty(self):
        """高波動度應扣風險管理分。"""
        calc = HealthScoreCalculator()
        result = calc.calculate(
            positions={
                "2330": {"weight_pct": 50.0},
                "2317": {"weight_pct": 50.0},
            },
            cash_ratio=0.15,
            turnover_rate=0.3,
            total_return_pct=5.0,
            num_stocks=2,
            trade_count=2,
            total_trades=4,
            volatility_pct=30.0,
        )
        # 波動度 > 25% 應扣分
        assert result.breakdown.get("risk_management", 15) < 15.0

    def test_large_drawdown_penalty(self):
        """大回撤應扣風險管理分。"""
        calc = HealthScoreCalculator()
        result = calc.calculate(
            positions={
                "2330": {"weight_pct": 50.0},
                "2317": {"weight_pct": 50.0},
            },
            cash_ratio=0.15,
            turnover_rate=0.3,
            total_return_pct=5.0,
            num_stocks=2,
            trade_count=2,
            total_trades=4,
            max_drawdown_pct=25.0,
        )
        # 回撤 > 20% 應扣分
        assert result.breakdown.get("risk_management", 15) < 15.0

    def test_negative_sharpe_penalty(self):
        """負 Sharpe Ratio 應扣風險管理分。"""
        calc = HealthScoreCalculator()
        result = calc.calculate(
            positions={
                "2330": {"weight_pct": 50.0},
                "2317": {"weight_pct": 50.0},
            },
            cash_ratio=0.15,
            turnover_rate=0.3,
            total_return_pct=5.0,
            num_stocks=2,
            trade_count=2,
            total_trades=4,
            sharpe_ratio=-0.5,
        )
        # Sharpe 為負值應扣分
        assert result.breakdown.get("risk_management", 15) < 15.0

    def test_no_trades_penalty(self):
        """完全無交易應扣交易紀律分。"""
        calc = HealthScoreCalculator()
        result = calc.calculate(
            positions={
                "2330": {"weight_pct": 50.0},
                "2317": {"weight_pct": 50.0},
            },
            cash_ratio=0.15,
            turnover_rate=0.0,
            total_return_pct=5.0,
            num_stocks=2,
            trade_count=0,
            total_trades=0,
        )
        # 無交易應扣 5 分
        assert result.breakdown.get("trading_discipline", 10) < 10.0

    def test_empty_positions(self):
        """無任何持股應得低分。"""
        calc = HealthScoreCalculator()
        result = calc.calculate(
            positions={},
            cash_ratio=1.0,
            turnover_rate=0.0,
            total_return_pct=0.0,
            num_stocks=0,
            trade_count=0,
            total_trades=0,
        )
        # 集中度分應為 0
        assert result.breakdown.get("concentration_risk", 20) == 0.0

    def test_to_dict_structure(self):
        """to_dict 應回傳正確的 JSON 結構。"""
        calc = HealthScoreCalculator()
        result = calc.calculate(
            positions={
                "2330": {"weight_pct": 50.0},
                "2317": {"weight_pct": 50.0},
            },
            cash_ratio=0.15,
            turnover_rate=0.3,
            total_return_pct=5.0,
            num_stocks=2,
            trade_count=2,
            total_trades=4,
            calculation_date=date(2024, 1, 15),
        )
        d = result.to_dict()
        assert "total_score" in d
        assert "max_score" in d
        assert "breakdown" in d
        assert "deductions" in d
        assert "calculation_date" in d
        assert d["max_score"] == 100.0
        assert d["calculation_date"] == "2024-01-15"

        # 驗證扣分原因結構
        for deduction in d["deductions"]:
            assert "dimension" in deduction
            assert "reason" in deduction
            assert "points_deducted" in deduction
            assert "severity" in deduction


# =========================================================================
# 4. DashboardService DAG 整合測試
# =========================================================================


class TestDashboardServiceDAG:
    """驗證 DashboardService 的 DAG 引擎整合。"""

    def test_summary_contains_health_score(self):
        """get_summary 應包含 health_score。"""
        service = DashboardService()
        events = [
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
            _make_buy_event("EVT-002", "2317", date(2024, 1, 3), 2000, 100.0),
        ]
        market_data = {
            "2330": _make_market_data(
                "2330",
                ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
                [580.0, 590.0, 585.0, 600.0],
            ),
            "2317": _make_market_data(
                "2317",
                ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
                [100.0, 105.0, 110.0, 115.0],
            ),
        }
        service.load_from_data(events, market_data, initial_cash=1_000_000.0)

        result = service.get_summary()

        # 應包含 health_score
        assert "health_score" in result
        hs = result["health_score"]
        assert "total_score" in hs
        assert "max_score" in hs
        assert "breakdown" in hs
        assert "deductions" in hs
        assert hs["max_score"] == 100.0

        # 分數應在合理範圍內
        assert 0 <= hs["total_score"] <= 100

    def test_health_score_with_single_stock(self):
        """單一股票時健康評分應較低。"""
        service = DashboardService()
        events = [
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
        ]
        market_data = {
            "2330": _make_market_data(
                "2330",
                ["2024-01-02", "2024-01-15"],
                [580.0, 600.0],
            ),
        }
        service.load_from_data(events, market_data, initial_cash=1_000_000.0)

        result = service.get_summary()
        hs = result["health_score"]

        # 單一股票 100% 集中，分數應低於雙股票情境
        assert hs["total_score"] < 85.0

        # 應有集中度扣分
        deductions_con = [
            d for d in hs["deductions"]
            if d["dimension"] == "concentration_risk"
        ]
        assert len(deductions_con) > 0

    def test_health_score_with_empty_portfolio(self):
        """空投資組合的健康評分。"""
        service = DashboardService()
        service.load_from_data([], {}, initial_cash=1_000_000.0)

        result = service.get_summary()
        hs = result["health_score"]

        # 空投資組合應有集中度扣分（無持股）
        assert hs["total_score"] < 100.0

    def test_dag_execution_no_errors(self):
        """DAG 執行不應有錯誤。"""
        service = DashboardService()
        events = [
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
            _make_buy_event("EVT-002", "2317", date(2024, 1, 3), 2000, 100.0),
        ]
        market_data = {
            "2330": _make_market_data(
                "2330",
                ["2024-01-02", "2024-01-05"],
                [580.0, 600.0],
            ),
            "2317": _make_market_data(
                "2317",
                ["2024-01-02", "2024-01-05"],
                [100.0, 115.0],
            ),
        }
        service.load_from_data(events, market_data, initial_cash=1_000_000.0)

        # 直接執行 DAG 驗證無錯誤
        bundle = service.resolver.resolve(
            service.registry,
            inputs={
                "engine": service.engine,
                "events": service.events,
                "market_data": service.market_data,
                "initial_cash": service.initial_cash,
                "target_date": None,
                "price_col": "adj_close",
            },
        )

        assert not bundle.has_errors(), f"DAG errors: {bundle.errors}"
        assert "NAV_SUMMARY" in bundle
        assert "HEALTH_SCORE" in bundle
        assert "ALLOCATION" in bundle
