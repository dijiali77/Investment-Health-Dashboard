"""
雙階段股利會計引擎測試

驗證 PortfolioEngine 的 DividendReceivable 雙階段邏輯：
1. 第一階段（除權息日）：正確衍生應收股利
2. 第二階段（發放日）：應收股利銷帳，現金增加
3. NAV 計算：除權息日後 NAV 包含應收股利，發放日現金正確增加
"""

from datetime import date
from typing import Dict, List

import pandas as pd
import pytest

from src.ledger.domain_models import (
    DividendEvent,
    EventType,
    FinancialEvent,
    SecurityTradeEvent,
    TradeCategory,
    Market,
)
from src.portfolio import PortfolioEngine
from src.accounting import DividendReceivable
from src.metrics.nav_history import NavHistoryGenerator
from src.api.dashboard_service import DashboardService


# =========================================================================
# 輔助函數
# =========================================================================


def _make_buy(
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


def _make_dividend_stage1(
    event_id: str, stock_id: str, ex_date: date,
    dps: float, shares: int, tax: float = 0.0,
) -> DividendEvent:
    """第一階段股利事件（除權息日 = 事件日期）。"""
    return DividendEvent(
        event_id=event_id,
        event_date=ex_date,
        sequence_in_day=10,
        event_type=EventType.DIVIDEND_RECEIVE,
        cash_impact=0.0,  # 第一階段不影響現金
        source_ref=f"test:{event_id}",
        stock_id=stock_id,
        dividend_per_share=dps,
        total_shares=shares,
        withholding_tax=tax,
        ex_dividend_date=ex_date,
    )


def _make_dividend_stage2(
    event_id: str, stock_id: str, payment_date: date,
    ex_date: date, dps: float, shares: int, tax: float = 0.0,
) -> DividendEvent:
    """第二階段股利事件（發放日 > 除權息日）。"""
    return DividendEvent(
        event_id=event_id,
        event_date=payment_date,
        sequence_in_day=10,
        event_type=EventType.DIVIDEND_RECEIVE,
        cash_impact=shares * dps - tax,  # 第二階段現金入帳
        source_ref=f"test:{event_id}",
        stock_id=stock_id,
        dividend_per_share=dps,
        total_shares=shares,
        withholding_tax=tax,
        ex_dividend_date=ex_date,
    )


def _make_market_data(stock_id: str, dates: List[date], prices: List[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(dates),
        "adj_close": prices,
    })


# =========================================================================
# 測試：DividendReceivable 領域模型
# =========================================================================


class TestDividendReceivableModel:
    """驗證 DividendReceivable frozen dataclass 的不可變性與自動計算。"""

    def test_create_receivable(self):
        """建立應收股利記錄。"""
        dr = DividendReceivable(
            receivable_id="DR-EVT-001",
            stock_id="2330",
            ex_dividend_date=date(2024, 7, 1),
            payment_date=date(2024, 8, 1),
            total_shares=2000,
            dividend_per_share=3.0,
            gross_amount=6000.0,
            withholding_tax=600.0,
            net_amount=5400.0,
            is_settled=False,
        )
        assert dr.receivable_id == "DR-EVT-001"
        assert dr.stock_id == "2330"
        assert dr.gross_amount == 6000.0
        assert dr.net_amount == 5400.0
        assert not dr.is_settled

    def test_auto_net_amount(self):
        """若未提供 net_amount，應自動計算。"""
        dr = DividendReceivable(
            receivable_id="DR-EVT-002",
            stock_id="2317",
            ex_dividend_date=date(2024, 7, 15),
            payment_date=date(2024, 8, 15),
            total_shares=3000,
            dividend_per_share=2.0,
            gross_amount=6000.0,
            withholding_tax=300.0,
            # net_amount 未提供，應自動計算
        )
        assert dr.net_amount == 5700.0  # 6000 - 300

    def test_frozen_immutable(self):
        """驗證 frozen=True 不可變更。"""
        dr = DividendReceivable(
            receivable_id="DR-EVT-003",
            stock_id="2454",
            ex_dividend_date=date(2024, 6, 1),
            payment_date=date(2024, 7, 1),
            total_shares=500,
            dividend_per_share=5.0,
            gross_amount=2500.0,
        )
        with pytest.raises(AttributeError):
            dr.is_settled = True  # 應拋出錯誤

    def test_settle_returns_new_instance(self):
        """settle() 應回傳新實例，不修改原實例。"""
        dr = DividendReceivable(
            receivable_id="DR-EVT-004",
            stock_id="2330",
            ex_dividend_date=date(2024, 7, 1),
            payment_date=date(2024, 8, 1),
            total_shares=2000,
            dividend_per_share=3.0,
            gross_amount=6000.0,
        )
        settled = dr.settle()

        # 原實例不變
        assert not dr.is_settled
        # 新實例已銷帳
        assert settled.is_settled
        assert settled.receivable_id == dr.receivable_id
        assert settled.net_amount == dr.net_amount


# =========================================================================
# 測試：PortfolioEngine 雙階段股利處理
# =========================================================================


class TestPortfolioEngineDividend:
    """驗證 PortfolioEngine 的雙階段股利會計邏輯。"""

    def setup_method(self):
        self.engine = PortfolioEngine()

    def _buy_and_process(self, stock_id: str, qty: int, price: float, d: date):
        """輔助：買入並處理。"""
        evt = _make_buy(f"BUY-{stock_id}-{d.isoformat()}", stock_id, d, qty, price)
        self.engine._process_single_event(evt)

    def test_stage1_creates_receivable(self):
        """第一階段：除權息日應產生應收股利。"""
        # 先買入 2000 股 2330
        self._buy_and_process("2330", 2000, 580.0, date(2024, 1, 2))

        # 除權息日：每股配 3.0 元
        div_evt = _make_dividend_stage1(
            "DIV-001", "2330", date(2024, 7, 1), 3.0, 2000,
        )
        result = self.engine._handle_dividend(div_evt)

        assert result is not None
        assert result.stock_id == "2330"
        assert result.total_shares == 2000
        assert result.gross_amount == 6000.0  # 2000 * 3.0
        assert result.net_amount == 6000.0  # 無扣繳稅
        assert not result.is_settled

        # 確認已加入引擎的追蹤列表
        assert len(self.engine.dividend_receivables) == 1
        assert self.engine.dividend_receivables[0].receivable_id == "DR-DIV-001"

    def test_stage1_with_tax(self):
        """第一階段：含扣繳稅的應收股利。"""
        self._buy_and_process("2330", 1000, 600.0, date(2024, 1, 2))

        div_evt = _make_dividend_stage1(
            "DIV-002", "2330", date(2024, 7, 1), 5.0, 1000, tax=500.0,
        )
        result = self.engine._handle_dividend(div_evt)

        assert result is not None
        assert result.gross_amount == 5000.0  # 1000 * 5.0
        assert result.withholding_tax == 500.0
        assert result.net_amount == 4500.0  # 5000 - 500

    def test_stage1_no_holding(self):
        """第一階段：若無持股，不產生應收股利。"""
        div_evt = _make_dividend_stage1(
            "DIV-003", "2330", date(2024, 7, 1), 3.0, 0,
        )
        result = self.engine._handle_dividend(div_evt)
        assert result is None
        assert len(self.engine.dividend_receivables) == 0

    def test_stage2_settles_receivable(self):
        """第二階段：發放日應銷帳應收股利。"""
        # 先買入
        self._buy_and_process("2330", 2000, 580.0, date(2024, 1, 2))

        # 第一階段：除權息日 7/1
        div1 = _make_dividend_stage1(
            "DIV-004", "2330", date(2024, 7, 1), 3.0, 2000,
        )
        self.engine._handle_dividend(div1)

        # 第二階段：發放日 8/1
        div2 = _make_dividend_stage2(
            "DIV-005", "2330", date(2024, 8, 1),
            date(2024, 7, 1), 3.0, 2000,
        )
        result = self.engine._handle_dividend(div2)

        assert result is not None
        assert result.is_settled
        assert result.payment_date == date(2024, 8, 1)
        assert result.net_amount == 6000.0

        # 確認引擎中的記錄已更新為已銷帳
        dr = self.engine.dividend_receivables[0]
        assert dr.is_settled
        assert dr.payment_date == date(2024, 8, 1)

    def test_stage2_no_matching_receivable(self):
        """第二階段：若無對應的未銷帳應收股利，回傳 None。"""
        div2 = _make_dividend_stage2(
            "DIV-006", "2330", date(2024, 8, 1),
            date(2024, 7, 1), 3.0, 2000,
        )
        result = self.engine._handle_dividend(div2)
        assert result is None

    def test_process_events_integration(self):
        """整合測試：process_events 完整處理雙階段股利。"""
        events = [
            _make_buy("EVT-001", "2330", date(2024, 1, 2), 2000, 580.0),
            _make_dividend_stage1(
                "EVT-002", "2330", date(2024, 7, 1), 3.0, 2000,
            ),
            _make_dividend_stage2(
                "EVT-003", "2330", date(2024, 8, 1),
                date(2024, 7, 1), 3.0, 2000,
            ),
        ]

        self.engine.process_events(events)

        # 確認應收股利記錄
        assert len(self.engine.dividend_receivables) == 1
        dr = self.engine.dividend_receivables[0]
        assert dr.is_settled
        assert dr.net_amount == 6000.0

        # 確認持股不受影響
        assert self.engine.accountant.get_total_quantity("2330") == 2000

    def test_reset_clears_receivables(self):
        """reset() 應清除所有應收股利記錄。"""
        self._buy_and_process("2330", 2000, 580.0, date(2024, 1, 2))
        div1 = _make_dividend_stage1(
            "DIV-007", "2330", date(2024, 7, 1), 3.0, 2000,
        )
        self.engine._handle_dividend(div1)
        assert len(self.engine.dividend_receivables) == 1

        self.engine.reset()
        assert len(self.engine.dividend_receivables) == 0


# =========================================================================
# 測試：NAV 計算包含應收股利
# =========================================================================


class TestNavWithDividendReceivable:
    """驗證 NAV 計算中應收股利的影響。"""

    def test_nav_includes_receivable_before_payment(self):
        """
        除權息日後、發放日前：
        - 應收股利已產生（但現金未動）
        - NAV 應包含應收股利（透過現金 + 市值計算）
        """
        engine = PortfolioEngine()
        nav_gen = NavHistoryGenerator(engine)

        events = [
            _make_buy("EVT-001", "2330", date(2024, 1, 2), 2000, 580.0),
            # 第一階段：除權息日 7/1，每股 3.0 元
            _make_dividend_stage1(
                "EVT-002", "2330", date(2024, 7, 1), 3.0, 2000,
            ),
            # 第二階段：發放日 8/1
            _make_dividend_stage2(
                "EVT-003", "2330", date(2024, 8, 1),
                date(2024, 7, 1), 3.0, 2000,
            ),
        ]

        market_data = {
            "2330": _make_market_data(
                "2330",
                [date(2024, 1, 2), date(2024, 7, 1), date(2024, 8, 1)],
                [580.0, 600.0, 620.0],
            ),
        }

        df = nav_gen.generate(
            events=events,
            market_data=market_data,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 8, 1),
            initial_cash=1_000_000.0,
        )

        # 1/2 買入後：市值 = 2000 * 580 = 1,160,000，現金 = 1,000,000 - 1,160,000 = -160,000
        # NAV = 1,160,000 + (-160,000) = 1,000,000
        nav_jan2 = df.loc[date(2024, 1, 2)]
        assert nav_jan2["market_value"] == 1_160_000.0
        assert nav_jan2["cash"] == -160_000.0
        assert nav_jan2["total_nav"] == 1_000_000.0

        # 7/1 除權息日：市值 = 2000 * 600 = 1,200,000
        # 現金 = -160,000（第一階段不影響現金）
        # NAV = 1,200,000 + (-160,000) = 1,040,000
        nav_jul1 = df.loc[date(2024, 7, 1)]
        assert nav_jul1["market_value"] == 1_200_000.0
        assert nav_jul1["cash"] == -160_000.0
        assert nav_jul1["total_nav"] == 1_040_000.0

        # 8/1 發放日：市值 = 2000 * 620 = 1,240,000
        # 現金 = -160,000 + 6,000（股利入帳）= -154,000
        # NAV = 1,240,000 + (-154,000) = 1,086,000
        nav_aug1 = df.loc[date(2024, 8, 1)]
        assert nav_aug1["market_value"] == 1_240_000.0
        assert nav_aug1["cash"] == -154_000.0
        assert nav_aug1["total_nav"] == 1_086_000.0

    def test_multiple_dividends_same_stock(self):
        """同一檔股票多次配息：每次除權息日獨立產生應收股利。"""
        engine = PortfolioEngine()
        nav_gen = NavHistoryGenerator(engine)

        events = [
            _make_buy("EVT-001", "2330", date(2024, 1, 2), 2000, 580.0),
            # 第一次配息：除權息 7/1，發放 8/1
            _make_dividend_stage1(
                "EVT-002", "2330", date(2024, 7, 1), 3.0, 2000,
            ),
            _make_dividend_stage2(
                "EVT-003", "2330", date(2024, 8, 1),
                date(2024, 7, 1), 3.0, 2000,
            ),
            # 第二次配息：除權息 12/1，發放 12/31
            _make_dividend_stage1(
                "EVT-004", "2330", date(2024, 12, 1), 2.5, 2000,
            ),
            _make_dividend_stage2(
                "EVT-005", "2330", date(2024, 12, 31),
                date(2024, 12, 1), 2.5, 2000,
            ),
        ]

        market_data = {
            "2330": _make_market_data(
                "2330",
                [date(2024, 1, 2), date(2024, 7, 1), date(2024, 8, 1),
                 date(2024, 12, 1), date(2024, 12, 31)],
                [580.0, 600.0, 620.0, 650.0, 680.0],
            ),
        }

        df = nav_gen.generate(
            events=events,
            market_data=market_data,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            initial_cash=1_000_000.0,
        )

        # 第一次股利入帳後：現金 = -160,000 + 6,000 = -154,000
        nav_aug1 = df.loc[date(2024, 8, 1)]
        assert nav_aug1["cash"] == -154_000.0

        # 第二次股利入帳後：現金 = -154,000 + 5,000 = -149,000
        nav_dec31 = df.loc[date(2024, 12, 31)]
        assert nav_dec31["cash"] == -149_000.0
        assert nav_dec31["total_nav"] == 1_211_000.0  # 2000*680 + (-149,000)


# =========================================================================
# 測試：DashboardService 整合應收股利
# =========================================================================


class TestDashboardServiceDividend:
    """驗證 DashboardService 中應收股利的整合。"""

    def test_dividend_receivable_in_service(self):
        """DashboardService 應正確追蹤應收股利。"""
        service = DashboardService()

        events = [
            _make_buy("EVT-001", "2330", date(2024, 1, 2), 2000, 580.0),
            _make_dividend_stage1(
                "EVT-002", "2330", date(2024, 7, 1), 3.0, 2000,
            ),
            _make_dividend_stage2(
                "EVT-003", "2330", date(2024, 8, 1),
                date(2024, 7, 1), 3.0, 2000,
            ),
        ]

        market_data = {
            "2330": _make_market_data(
                "2330",
                [date(2024, 1, 2), date(2024, 7, 1), date(2024, 8, 1)],
                [580.0, 600.0, 620.0],
            ),
        }

        service.load_from_data(events, market_data, initial_cash=1_000_000.0)

        # 確認引擎中有應收股利記錄
        assert len(service.engine.dividend_receivables) == 1
        dr = service.engine.dividend_receivables[0]
        assert dr.is_settled
        assert dr.net_amount == 6000.0

        # 確認現金餘額已包含股利入帳
        cash = service._calculate_cash_balance()
        assert cash == -154_000.0  # 1,000,000 - 1,160,000 + 6,000

    def test_dividend_receivable_method(self):
        """_calculate_dividend_receivable() 應正確計算未銷帳應收。"""
        service = DashboardService()

        events = [
            _make_buy("EVT-001", "2330", date(2024, 1, 2), 2000, 580.0),
            # 第一階段：除權息日 7/1，但尚未有第二階段
            _make_dividend_stage1(
                "EVT-002", "2330", date(2024, 7, 1), 3.0, 2000,
            ),
        ]

        market_data = {
            "2330": _make_market_data(
                "2330",
                [date(2024, 1, 2), date(2024, 7, 1)],
                [580.0, 600.0],
            ),
        }

        service.load_from_data(events, market_data, initial_cash=1_000_000.0)

        # 除權息日後，應有未銷帳應收股利 6,000
        receivable = service._calculate_dividend_receivable(
            target_date=date(2024, 7, 1)
        )
        assert receivable == 6000.0

        # 除權息日前，應無應收股利
        receivable_before = service._calculate_dividend_receivable(
            target_date=date(2024, 6, 30)
        )
        assert receivable_before == 0.0

    def test_summary_with_dividend(self):
        """get_summary() 在有股利事件時應正確計算。"""
        service = DashboardService()

        events = [
            _make_buy("EVT-001", "2330", date(2024, 1, 2), 2000, 580.0),
            _make_dividend_stage1(
                "EVT-002", "2330", date(2024, 7, 1), 3.0, 2000,
            ),
            _make_dividend_stage2(
                "EVT-003", "2330", date(2024, 8, 1),
                date(2024, 7, 1), 3.0, 2000,
            ),
        ]

        market_data = {
            "2330": _make_market_data(
                "2330",
                [date(2024, 1, 2), date(2024, 7, 1), date(2024, 8, 1)],
                [580.0, 600.0, 620.0],
            ),
        }

        service.load_from_data(events, market_data, initial_cash=1_000_000.0)

        # 查詢 8/1 的摘要
        summary = service.get_summary(target_date=date(2024, 8, 1))

        assert summary["total_market_value"] == 1_240_000.0  # 2000 * 620
        assert summary["cash_balance"] == -154_000.0  # 含股利入帳
        assert summary["total_nav"] == 1_086_000.0  # 1,240,000 + (-154,000)
        assert summary["total_return_pct"] == 8.6  # (1,086,000 - 1,000,000) / 1,000,000 * 100
