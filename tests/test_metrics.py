"""
Metrics Layer 單元測試

測試範圍：
1. UnrealizedPnlCalculator：
   - 單一股票未實現損益計算（最新價格）
   - 單一股票未實現損益計算（指定日期 + LOCF）
   - 多檔股票未實現損益匯總
   - 無持股時回傳空結果
   - 無市場資料時回傳空結果
   - 未實現損益時間序列
2. AssetAllocationCalculator：
   - 單一股票權重 100%
   - 多檔股票權重計算
   - 權重排序（降序）
   - 時間序列
3. NavHistoryGenerator：
   - 無事件時的淨值曲線
   - 單一買入事件後的淨值曲線
   - 買入後賣出的淨值曲線
   - 多檔股票的淨值曲線
   - 現金餘額追蹤
   - 日報酬率與累積報酬率計算
"""

import pytest
from datetime import date, timedelta

import pandas as pd

from src.backend.metrics import (
    UnrealizedPnlCalculator,
    AssetAllocationCalculator,
    NavHistoryGenerator,
)
from src.backend.portfolio_engine import PortfolioEngine
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


def _make_sell_event(
    event_id: str, stock_id: str, event_date: date,
    quantity: int, price: float,
) -> SecurityTradeEvent:
    return SecurityTradeEvent(
        event_id=event_id,
        event_date=event_date,
        sequence_in_day=2,
        event_type=EventType.SECURITY_SELL,
        cash_impact=quantity * price,
        source_ref=f"test:{event_id}",
        stock_id=stock_id,
        stock_name=f"Stock-{stock_id}",
        quantity=quantity,
        price=price,
        fee=0.0,
        tax=0.0,
        trade_category=TradeCategory.BOARD_LOT,
        market=Market.TWSE,
        settlement_date=event_date,
    )


def _make_market_data(
    stock_id: str,
    dates: list,
    prices: list,
    price_col: str = "adj_close",
) -> pd.DataFrame:
    """建立測試用市場資料。"""
    return pd.DataFrame({
        "date": pd.to_datetime(dates),
        price_col: prices,
    })


def _make_engine_with_events(events) -> PortfolioEngine:
    """建立已處理事件的 PortfolioEngine。"""
    engine = PortfolioEngine()
    engine.process_events(events)
    return engine


# =========================================================================
# 1. UnrealizedPnlCalculator 測試
# =========================================================================


class TestUnrealizedPnlCalculator:
    """未實現損益計算器測試。"""

    def test_single_stock_latest_price(self):
        """單一股票，使用最新價格計算未實現損益。"""
        engine = _make_engine_with_events([
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
        ])
        calculator = UnrealizedPnlCalculator(engine)

        market_data = {
            "2330": _make_market_data(
                "2330",
                ["2024-01-02", "2024-01-15"],
                [580.0, 600.0],
            ),
        }

        result = calculator.calculate(market_data)

        assert "2330" in result["positions"]
        pos = result["positions"]["2330"]
        assert pos["quantity"] == 1000
        assert pos["avg_cost"] == 580.0
        assert pos["current_price"] == 600.0
        assert pos["cost_basis"] == 580_000.0
        assert pos["market_value"] == 600_000.0
        assert pos["unrealized_pnl"] == 20_000.0
        assert pos["unrealized_pnl_pct"] == pytest.approx(3.45, rel=0.01)

        assert result["total_market_value"] == 600_000.0
        assert result["total_cost"] == 580_000.0
        assert result["total_unrealized_pnl"] == 20_000.0

    def test_single_stock_target_date_with_locf(self):
        """指定目標日期，透過 LOCF 補值計算未實現損益。"""
        engine = _make_engine_with_events([
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
        ])
        calculator = UnrealizedPnlCalculator(engine)

        # 市場資料只有 1/2 和 1/5，目標日期 1/4 需 LOCF
        market_data = {
            "2330": _make_market_data(
                "2330",
                ["2024-01-02", "2024-01-05"],
                [580.0, 600.0],
            ),
        }

        result = calculator.calculate(
            market_data, target_date=date(2024, 1, 4)
        )

        pos = result["positions"]["2330"]
        # 1/4 無資料，LOCF 取 1/2 的價格 580
        assert pos["current_price"] == 580.0
        assert pos["unrealized_pnl"] == 0.0

    def test_target_date_before_first_data(self):
        """目標日期早於市場資料起始日，應回傳 None。"""
        engine = _make_engine_with_events([
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
        ])
        calculator = UnrealizedPnlCalculator(engine)

        market_data = {
            "2330": _make_market_data(
                "2330",
                ["2024-01-05"],
                [600.0],
            ),
        }

        result = calculator.calculate(
            market_data, target_date=date(2024, 1, 2)
        )

        # 1/2 早於市場資料起始日 1/5，無法取得價格
        assert "2330" not in result["positions"]
        assert result["total_market_value"] == 0.0

    def test_multiple_stocks(self):
        """多檔股票未實現損益匯總。"""
        engine = _make_engine_with_events([
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
            _make_buy_event("EVT-002", "2317", date(2024, 1, 3), 2000, 100.0),
        ])
        calculator = UnrealizedPnlCalculator(engine)

        market_data = {
            "2330": _make_market_data("2330", ["2024-01-15"], [600.0]),
            "2317": _make_market_data("2317", ["2024-01-15"], [110.0]),
        }

        result = calculator.calculate(market_data)

        assert len(result["positions"]) == 2
        # 2330: 1000 * (600 - 580) = 20_000
        assert result["positions"]["2330"]["unrealized_pnl"] == 20_000.0
        # 2317: 2000 * (110 - 100) = 20_000
        assert result["positions"]["2317"]["unrealized_pnl"] == 20_000.0
        # 總計: 40_000
        assert result["total_unrealized_pnl"] == 40_000.0
        assert result["total_market_value"] == 600_000 + 220_000

    def test_no_positions(self):
        """無持股時應回傳空結果。"""
        engine = PortfolioEngine()
        calculator = UnrealizedPnlCalculator(engine)

        result = calculator.calculate({})

        assert result["positions"] == {}
        assert result["total_unrealized_pnl"] == 0.0
        assert result["total_market_value"] == 0.0
        assert result["total_cost"] == 0.0

    def test_no_market_data(self):
        """有持股但無市場資料時，該股票應被忽略。"""
        engine = _make_engine_with_events([
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
        ])
        calculator = UnrealizedPnlCalculator(engine)

        result = calculator.calculate({})

        assert result["positions"] == {}
        assert result["total_unrealized_pnl"] == 0.0

    def test_unrealized_pnl_with_loss(self):
        """股價下跌時未實現損益應為負數。"""
        engine = _make_engine_with_events([
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
        ])
        calculator = UnrealizedPnlCalculator(engine)

        market_data = {
            "2330": _make_market_data("2330", ["2024-01-15"], [550.0]),
        }

        result = calculator.calculate(market_data)

        pos = result["positions"]["2330"]
        assert pos["unrealized_pnl"] == -30_000.0
        assert pos["unrealized_pnl_pct"] == pytest.approx(-5.17, rel=0.01)

    def test_partial_sell_unrealized_pnl(self):
        """部分賣出後，剩餘 Lot 的未實現損益應正確。"""
        engine = _make_engine_with_events([
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
            _make_sell_event("EVT-002", "2330", date(2024, 1, 10), 300, 600.0),
        ])
        calculator = UnrealizedPnlCalculator(engine)

        market_data = {
            "2330": _make_market_data("2330", ["2024-01-15"], [620.0]),
        }

        result = calculator.calculate(market_data)

        pos = result["positions"]["2330"]
        assert pos["quantity"] == 700
        assert pos["avg_cost"] == 580.0
        assert pos["cost_basis"] == 406_000.0  # 580_000 * 0.7
        assert pos["market_value"] == 700 * 620.0
        assert pos["unrealized_pnl"] == 700 * 620.0 - 406_000.0

    def test_time_series(self):
        """未實現損益時間序列。"""
        engine = _make_engine_with_events([
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
        ])
        calculator = UnrealizedPnlCalculator(engine)

        market_data = {
            "2330": _make_market_data(
                "2330",
                ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
                [580.0, 590.0, 585.0, 600.0],
            ),
        }

        ts = calculator.calculate_time_series(
            market_data,
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 5),
        )

        assert len(ts) == 4  # 1/2 ~ 1/5 共 4 天
        # 1/2: 損益為 0（買入價 = 市價）
        assert ts.loc[date(2024, 1, 2), "unrealized_pnl"] == 0.0
        # 1/3: 1000 * (590 - 580) = 10_000
        assert ts.loc[date(2024, 1, 3), "unrealized_pnl"] == 10_000.0
        # 1/5: 1000 * (600 - 580) = 20_000
        assert ts.loc[date(2024, 1, 5), "unrealized_pnl"] == 20_000.0


# =========================================================================
# 2. AssetAllocationCalculator 測試
# =========================================================================


class TestAssetAllocationCalculator:
    """資產配置比例計算器測試。"""

    def test_single_stock_100_percent(self):
        """單一股票權重應為 100%。"""
        engine = _make_engine_with_events([
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
        ])
        calculator = AssetAllocationCalculator(engine)

        market_data = {
            "2330": _make_market_data("2330", ["2024-01-15"], [600.0]),
        }

        result = calculator.calculate(market_data)

        assert len(result["allocations"]) == 1
        assert result["allocations"][0]["stock_id"] == "2330"
        assert result["allocations"][0]["weight_pct"] == 100.0
        assert result["total_market_value"] == 600_000.0

    def test_multiple_stocks_weight(self):
        """多檔股票權重計算。"""
        engine = _make_engine_with_events([
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
            _make_buy_event("EVT-002", "2317", date(2024, 1, 3), 2000, 100.0),
        ])
        calculator = AssetAllocationCalculator(engine)

        market_data = {
            "2330": _make_market_data("2330", ["2024-01-15"], [600.0]),
            "2317": _make_market_data("2317", ["2024-01-15"], [110.0]),
        }

        result = calculator.calculate(market_data)

        assert len(result["allocations"]) == 2
        # 2330 市值 = 600_000, 2317 市值 = 220_000, 總市值 = 820_000
        # 2330 權重 = 600_000 / 820_000 ≈ 73.17%
        # 2317 權重 = 220_000 / 820_000 ≈ 26.83%
        assert result["allocations"][0]["stock_id"] == "2330"
        assert result["allocations"][0]["weight_pct"] == pytest.approx(73.17, rel=0.01)
        assert result["allocations"][1]["stock_id"] == "2317"
        assert result["allocations"][1]["weight_pct"] == pytest.approx(26.83, rel=0.01)

    def test_allocations_sorted_by_weight_desc(self):
        """權重應按降序排列。"""
        engine = _make_engine_with_events([
            _make_buy_event("EVT-001", "2317", date(2024, 1, 3), 2000, 100.0),
            _make_buy_event("EVT-002", "2330", date(2024, 1, 2), 1000, 580.0),
        ])
        calculator = AssetAllocationCalculator(engine)

        market_data = {
            "2330": _make_market_data("2330", ["2024-01-15"], [600.0]),
            "2317": _make_market_data("2317", ["2024-01-15"], [110.0]),
        }

        result = calculator.calculate(market_data)

        weights = [a["weight_pct"] for a in result["allocations"]]
        assert weights == sorted(weights, reverse=True)

    def test_no_positions(self):
        """無持股時應回傳空配置。"""
        engine = PortfolioEngine()
        calculator = AssetAllocationCalculator(engine)

        result = calculator.calculate({})

        assert result["allocations"] == []
        assert result["total_market_value"] == 0.0

    def test_time_series(self):
        """資產配置時間序列。"""
        engine = _make_engine_with_events([
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
            _make_buy_event("EVT-002", "2317", date(2024, 1, 3), 2000, 100.0),
        ])
        calculator = AssetAllocationCalculator(engine)

        market_data = {
            "2330": _make_market_data(
                "2330",
                ["2024-01-02", "2024-01-03", "2024-01-04"],
                [580.0, 590.0, 600.0],
            ),
            "2317": _make_market_data(
                "2317",
                ["2024-01-02", "2024-01-03", "2024-01-04"],
                [100.0, 105.0, 110.0],
            ),
        }

        ts = calculator.calculate_time_series(
            market_data,
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 4),
        )

        assert len(ts) == 3
        assert "2330" in ts.columns
        assert "2317" in ts.columns


# =========================================================================
# 3. NavHistoryGenerator 測試
# =========================================================================


class TestNavHistoryGenerator:
    """投資組合歷史淨值序列生成器測試。"""

    def test_no_events(self):
        """無事件時，淨值應僅包含期初現金。"""
        engine = PortfolioEngine()
        generator = NavHistoryGenerator(engine)

        result = generator.generate(
            events=[],
            market_data={},
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
            initial_cash=1_000_000.0,
        )

        assert len(result) == 5  # 1/1 ~ 1/5
        for idx in result.index:
            assert result.loc[idx, "cash"] == 1_000_000.0
            assert result.loc[idx, "market_value"] == 0.0
            assert result.loc[idx, "total_nav"] == 1_000_000.0

    def test_single_buy_then_nav(self):
        """買入後，淨值應反映市值變化。"""
        engine = PortfolioEngine()
        generator = NavHistoryGenerator(engine)

        events = [
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
        ]

        market_data = {
            "2330": _make_market_data(
                "2330",
                ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
                [580.0, 590.0, 585.0, 600.0],
            ),
        }

        result = generator.generate(
            events=events,
            market_data=market_data,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
            initial_cash=1_000_000.0,
        )

        # 1/1: 尚未買入，只有現金
        assert result.loc[date(2024, 1, 1), "cash"] == 1_000_000.0
        assert result.loc[date(2024, 1, 1), "market_value"] == 0.0
        assert result.loc[date(2024, 1, 1), "total_nav"] == 1_000_000.0

        # 1/2: 買入後，現金減少，市值 = 1000 * 580 = 580_000
        assert result.loc[date(2024, 1, 2), "cash"] == 1_000_000.0 - 580_000.0
        assert result.loc[date(2024, 1, 2), "market_value"] == 580_000.0
        assert result.loc[date(2024, 1, 2), "total_nav"] == 1_000_000.0

        # 1/3: 股價漲到 590，市值 = 590_000
        assert result.loc[date(2024, 1, 3), "market_value"] == 590_000.0
        assert result.loc[date(2024, 1, 3), "total_nav"] == 420_000.0 + 590_000.0

        # 1/5: 股價漲到 600，市值 = 600_000
        assert result.loc[date(2024, 1, 5), "market_value"] == 600_000.0

    def test_buy_then_sell_nav(self):
        """買入後賣出，淨值應正確反映實現損益。"""
        engine = PortfolioEngine()
        generator = NavHistoryGenerator(engine)

        events = [
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
            _make_sell_event("EVT-002", "2330", date(2024, 1, 10), 1000, 600.0),
        ]

        market_data = {
            "2330": _make_market_data(
                "2330",
                ["2024-01-02", "2024-01-10", "2024-01-15"],
                [580.0, 600.0, 610.0],
            ),
        }

        result = generator.generate(
            events=events,
            market_data=market_data,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 15),
            initial_cash=1_000_000.0,
        )

        # 1/1: 只有現金
        assert result.loc[date(2024, 1, 1), "total_nav"] == 1_000_000.0

        # 1/2: 買入後，淨值不變（買入價 = 市價）
        assert result.loc[date(2024, 1, 2), "total_nav"] == 1_000_000.0

        # 1/10: 賣出後，現金增加，無持股
        # 現金 = 1_000_000 - 580_000 + 600_000 = 1_020_000
        assert result.loc[date(2024, 1, 10), "cash"] == 1_020_000.0
        assert result.loc[date(2024, 1, 10), "market_value"] == 0.0
        assert result.loc[date(2024, 1, 10), "total_nav"] == 1_020_000.0

        # 1/15: 仍無持股，淨值不變
        assert result.loc[date(2024, 1, 15), "total_nav"] == 1_020_000.0

    def test_multiple_stocks_nav(self):
        """多檔股票的淨值曲線。"""
        engine = PortfolioEngine()
        generator = NavHistoryGenerator(engine)

        events = [
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
            _make_buy_event("EVT-002", "2317", date(2024, 1, 3), 2000, 100.0),
        ]

        market_data = {
            "2330": _make_market_data(
                "2330",
                ["2024-01-02", "2024-01-03", "2024-01-04"],
                [580.0, 590.0, 600.0],
            ),
            "2317": _make_market_data(
                "2317",
                ["2024-01-02", "2024-01-03", "2024-01-04"],
                [100.0, 105.0, 110.0],
            ),
        }

        result = generator.generate(
            events=events,
            market_data=market_data,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 4),
            initial_cash=1_000_000.0,
        )

        # 1/4: 2330 市值 = 600_000, 2317 市值 = 220_000
        # 現金 = 1_000_000 - 580_000 - 200_000 = 220_000
        # 總淨值 = 600_000 + 220_000 + 220_000 = 1_040_000
        assert result.loc[date(2024, 1, 4), "market_value"] == 820_000.0
        assert result.loc[date(2024, 1, 4), "cash"] == 220_000.0
        assert result.loc[date(2024, 1, 4), "total_nav"] == 1_040_000.0

        # 驗證個股市值欄位
        assert result.loc[date(2024, 1, 4), "2330"] == 600_000.0
        assert result.loc[date(2024, 1, 4), "2317"] == 220_000.0

    def test_daily_return_calculation(self):
        """日報酬率計算。"""
        engine = PortfolioEngine()
        generator = NavHistoryGenerator(engine)

        events = [
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
        ]

        market_data = {
            "2330": _make_market_data(
                "2330",
                ["2024-01-02", "2024-01-03", "2024-01-04"],
                [580.0, 580.0, 600.0],
            ),
        }

        result = generator.generate(
            events=events,
            market_data=market_data,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 4),
            initial_cash=1_000_000.0,
        )

        # 1/1: 無事件，無報酬率
        assert result.loc[date(2024, 1, 1), "daily_return_pct"] == 0.0

        # 1/2: 買入日，淨值不變
        assert result.loc[date(2024, 1, 2), "daily_return_pct"] == 0.0

        # 1/3: 股價不變，報酬率 0
        assert result.loc[date(2024, 1, 3), "daily_return_pct"] == 0.0

        # 1/4: 股價從 580 漲到 600，市值從 580_000 漲到 600_000
        # 前一日總淨值 = 420_000 + 580_000 = 1_000_000
        # 當日總淨值 = 420_000 + 600_000 = 1_020_000
        # 日報酬率 = (1_020_000 - 1_000_000) / 1_000_000 * 100 = 2.0%
        assert result.loc[date(2024, 1, 4), "daily_return_pct"] == pytest.approx(2.0, rel=0.01)

    def test_cumulative_return(self):
        """累積報酬率計算。"""
        engine = PortfolioEngine()
        generator = NavHistoryGenerator(engine)

        events = [
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
        ]

        market_data = {
            "2330": _make_market_data(
                "2330",
                ["2024-01-02", "2024-01-05"],
                [580.0, 600.0],
            ),
        }

        result = generator.generate(
            events=events,
            market_data=market_data,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
            initial_cash=1_000_000.0,
        )

        # 1/5: 總淨值 = 420_000 + 600_000 = 1_020_000
        # 初始淨值 = 1_000_000
        # 累積報酬率 = (1_020_000 - 1_000_000) / 1_000_000 * 100 = 2.0%
        assert result.loc[date(2024, 1, 5), "cumulative_return_pct"] == pytest.approx(2.0, rel=0.01)

    def test_nav_with_gap_in_market_data(self):
        """市場資料有缺口時，LOCF 應正確補值。"""
        engine = PortfolioEngine()
        generator = NavHistoryGenerator(engine)

        events = [
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
        ]

        # 市場資料只有 1/2 和 1/5，中間有缺口
        market_data = {
            "2330": _make_market_data(
                "2330",
                ["2024-01-02", "2024-01-05"],
                [580.0, 600.0],
            ),
        }

        result = generator.generate(
            events=events,
            market_data=market_data,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
            initial_cash=1_000_000.0,
        )

        # 1/3 和 1/4 應使用 LOCF 補值（沿用 1/2 的 580）
        assert result.loc[date(2024, 1, 3), "market_value"] == 580_000.0
        assert result.loc[date(2024, 1, 4), "market_value"] == 580_000.0
        # 1/5 使用實際價格 600
        assert result.loc[date(2024, 1, 5), "market_value"] == 600_000.0

    def test_empty_market_data(self):
        """無市場資料時，市值應為 0。"""
        engine = PortfolioEngine()
        generator = NavHistoryGenerator(engine)

        events = [
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
        ]

        result = generator.generate(
            events=events,
            market_data={},
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3),
            initial_cash=1_000_000.0,
        )

        # 有持股但無市場資料，市值為 0
        assert result.loc[date(2024, 1, 2), "market_value"] == 0.0
        assert result.loc[date(2024, 1, 2), "total_nav"] == 420_000.0  # 只有現金
