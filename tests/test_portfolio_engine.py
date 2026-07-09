"""
Portfolio Engine 單元測試

測試範圍：
1. Lot 資料模型（建立、屬性、稀釋）
2. RealizedPnL 資料模型
3. FifoAccountant FIFO 會計帳：
   - 單筆買入建 Lot
   - 多筆買入（多個 Lot）
   - 完全賣出（單 Lot 完全銷帳）
   - 部分賣出（單 Lot 部分銷帳 + 剩餘成本計算）
   - 跨 Lot 賣出（多個 Lot 依序銷帳）
   - 庫存不足與無庫存錯誤處理
   - 查詢介面（總股數、總成本、平均成本）
4. PortfolioEngine 事件驅動：
   - 接收 SecurityTradeEvent 序列
   - 正確驅動 FIFO 會計帳
   - 持倉摘要與損益摘要
"""

import pytest
from datetime import date
from decimal import Decimal

from src.backend.portfolio_engine import Lot, RealizedPnL, FifoAccountant, PortfolioEngine
from src.backend.ledger.domain_models import (
    SecurityTradeEvent, EventType, TradeCategory, Market,
)


# =========================================================================
# 1. Lot 資料模型測試
# =========================================================================


class TestLot:
    """Lot 資料模型的基本行為。"""

    def test_create_lot(self):
        """建立 Lot 並驗證屬性。"""
        lot = Lot(
            lot_id="LOT-000001",
            stock_id="2330",
            buy_date=date(2024, 1, 2),
            total_quantity=1000,
            remaining_quantity=1000,
            total_cost=580_000.0,
            remaining_cost=580_000.0,
            buy_price=580.0,
        )
        assert lot.lot_id == "LOT-000001"
        assert lot.stock_id == "2330"
        assert lot.total_quantity == 1000
        assert lot.remaining_quantity == 1000
        assert lot.total_cost == 580_000.0
        assert lot.remaining_cost == 580_000.0
        assert lot.buy_price == 580.0

    def test_is_closed_false_when_remaining(self):
        """尚有剩餘股數時，is_closed 應為 False。"""
        lot = Lot("L-1", "2330", date(2024, 1, 2), 1000, 500, 580_000, 290_000, 580.0)
        assert lot.is_closed is False

    def test_is_closed_true_when_zero(self):
        """剩餘股數為 0 時，is_closed 應為 True。"""
        lot = Lot("L-1", "2330", date(2024, 1, 2), 1000, 0, 580_000, 0.0, 580.0)
        assert lot.is_closed is True

    def test_avg_cost_per_share(self):
        """驗證每股平均成本計算。"""
        lot = Lot("L-1", "2330", date(2024, 1, 2), 1000, 500, 580_000, 290_000, 580.0)
        assert lot.avg_cost_per_share == 580.0  # 290_000 / 500

    def test_avg_cost_per_share_zero_when_closed(self):
        """完全賣出後，每股平均成本應為 0。"""
        lot = Lot("L-1", "2330", date(2024, 1, 2), 1000, 0, 580_000, 0.0, 580.0)
        assert lot.avg_cost_per_share == 0.0

    def test_lot_is_frozen(self):
        """Lot 應為 frozen（不可變）。"""
        lot = Lot("L-1", "2330", date(2024, 1, 2), 1000, 1000, 580_000, 580_000, 580.0)
        with pytest.raises(AttributeError):
            lot.remaining_quantity = 500

    def test_dilute_full_sale(self):
        """完全賣出：dilute 應回傳正確的實現損益。"""
        lot = Lot("L-1", "2330", date(2024, 1, 2), 1000, 1000, 580_000, 580_000, 580.0)
        pnl = lot.dilute(1000, 600.0)

        assert pnl.lot_id == "L-1"
        assert pnl.sold_quantity == 1000
        assert pnl.sold_price == 600.0
        assert pnl.cost_basis == 580_000.0  # 全部成本
        assert pnl.realized_pnl == 20_000.0  # 600*1000 - 580_000

    def test_dilute_partial_sale(self):
        """部分賣出：dilute 應按比例計算成本基礎。"""
        lot = Lot("L-1", "2330", date(2024, 1, 2), 1000, 1000, 580_000, 580_000, 580.0)
        pnl = lot.dilute(300, 600.0)

        assert pnl.sold_quantity == 300
        # 成本基礎 = 580_000 * (300/1000) = 174_000
        assert pnl.cost_basis == 174_000.0
        # 實現損益 = 300*600 - 174_000 = 6_000
        assert pnl.realized_pnl == 6_000.0

    def test_dilute_excess_quantity(self):
        """賣出股數超過剩餘股數時，只賣出剩餘股數。"""
        lot = Lot("L-1", "2330", date(2024, 1, 2), 1000, 500, 580_000, 290_000, 580.0)
        pnl = lot.dilute(1000, 600.0)

        assert pnl.sold_quantity == 500  # 只賣出剩餘的 500 股
        assert pnl.cost_basis == 290_000.0
        assert pnl.realized_pnl == 500 * 600.0 - 290_000.0

    def test_dilute_zero_quantity(self):
        """賣出 0 股時，實現損益應為 0。"""
        lot = Lot("L-1", "2330", date(2024, 1, 2), 1000, 1000, 580_000, 580_000, 580.0)
        pnl = lot.dilute(0, 600.0)

        assert pnl.sold_quantity == 0
        assert pnl.cost_basis == 0.0
        assert pnl.realized_pnl == 0.0

    def test_apply_dilution_stock_dividend(self):
        """股票股利稀釋：ratio=1.2，股數增加，成本不變。"""
        lot = Lot("L-1", "2330", date(2024, 1, 2), 1000, 1000, 580_000, 580_000, 580.0)
        diluted = lot.apply_dilution(1.2)

        assert diluted.total_quantity == 1200
        assert diluted.remaining_quantity == 1200
        assert diluted.total_cost == 580_000.0
        assert diluted.remaining_cost == 580_000.0
        # 每股成本 = 580_000 / 1200 ≈ 483.33
        assert diluted.buy_price == pytest.approx(580_000 / 1200)

    def test_apply_dilution_stock_split(self):
        """股票分割：ratio=2.0，股數加倍，成本不變。"""
        lot = Lot("L-1", "2330", date(2024, 1, 2), 1000, 1000, 580_000, 580_000, 580.0)
        diluted = lot.apply_dilution(2.0)

        assert diluted.total_quantity == 2000
        assert diluted.remaining_quantity == 2000
        assert diluted.buy_price == 290.0  # 580_000 / 2000

    def test_apply_dilution_stock_merge(self):
        """股票合併：ratio=0.5，股數減半，成本不變。"""
        lot = Lot("L-1", "2330", date(2024, 1, 2), 1000, 1000, 580_000, 580_000, 580.0)
        diluted = lot.apply_dilution(0.5)

        assert diluted.total_quantity == 500
        assert diluted.remaining_quantity == 500
        assert diluted.buy_price == 1160.0  # 580_000 / 500


# =========================================================================
# 2. RealizedPnL 資料模型測試
# =========================================================================


class TestRealizedPnL:
    """RealizedPnL 資料模型的基本行為。"""

    def test_create_realized_pnl(self):
        """建立 RealizedPnL 並驗證屬性。"""
        pnl = RealizedPnL(
            lot_id="L-1",
            sold_quantity=300,
            sold_price=600.0,
            cost_basis=174_000.0,
            realized_pnl=6_000.0,
        )
        assert pnl.lot_id == "L-1"
        assert pnl.sold_quantity == 300
        assert pnl.sold_price == 600.0
        assert pnl.cost_basis == 174_000.0
        assert pnl.realized_pnl == 6_000.0

    def test_realized_pnl_is_frozen(self):
        """RealizedPnL 應為 frozen。"""
        pnl = RealizedPnL("L-1", 300, 600.0, 174_000.0, 6_000.0)
        with pytest.raises(AttributeError):
            pnl.realized_pnl = 0.0


# =========================================================================
# 3. FifoAccountant 測試
# =========================================================================


class TestFifoAccountant:
    """FIFO 會計帳的核心邏輯測試。"""

    def test_add_buy_creates_lot(self):
        """買入應建立 Lot 並加入佇列。"""
        acc = FifoAccountant()
        lot = acc.add_buy("LOT-000001", "2330", date(2024, 1, 2), 1000, 580.0, fee=20)

        assert lot.lot_id == "LOT-000001"
        assert lot.stock_id == "2330"
        assert lot.total_quantity == 1000
        assert lot.remaining_quantity == 1000
        assert lot.total_cost == 580_020.0  # 1000*580 + 20
        assert lot.remaining_cost == 580_020.0

    def test_add_buy_multiple_lots(self):
        """多筆買入應建立多個 Lot，按 FIFO 順序排列。"""
        acc = FifoAccountant()
        acc.add_buy("LOT-000001", "2330", date(2024, 1, 2), 1000, 580.0)
        acc.add_buy("LOT-000002", "2330", date(2024, 1, 15), 500, 600.0)

        lots = acc.get_lots("2330")
        assert len(lots) == 2
        assert lots[0].lot_id == "LOT-000001"  # 先買入的在前面
        assert lots[1].lot_id == "LOT-000002"

    def test_sell_full_lot(self):
        """完全賣出一個 Lot。"""
        acc = FifoAccountant()
        acc.add_buy("LOT-000001", "2330", date(2024, 1, 2), 1000, 580.0)

        pnls = acc.add_sell("2330", 1000, 600.0)

        assert len(pnls) == 1
        assert pnls[0].realized_pnl == 20_000.0  # 600*1000 - 580*1000
        assert acc.get_total_quantity("2330") == 0
        # 完全賣出後 Lot 從佇列中移除，但仍在 realized_pnls 中有記錄
        assert len(acc.get_lots("2330")) == 0

    def test_partial_sell_single_lot(self):
        """
        部分賣出：賣出 300 股，剩餘 700 股。
        驗證剩餘成本與平均成本正確。
        """
        acc = FifoAccountant()
        acc.add_buy("LOT-000001", "2330", date(2024, 1, 2), 1000, 580.0)

        pnls = acc.add_sell("2330", 300, 600.0)

        # 實現損益
        assert len(pnls) == 1
        assert pnls[0].realized_pnl == 6_000.0  # 300*600 - 300*580

        # 剩餘持股
        assert acc.get_total_quantity("2330") == 700
        remaining_lot = acc.get_lots("2330")[0]
        assert remaining_lot.remaining_quantity == 700
        # 剩餘成本 = 580_000 * (700/1000) = 406_000
        assert remaining_lot.remaining_cost == 406_000.0
        # 平均成本不變 = 580.0
        assert remaining_lot.avg_cost_per_share == 580.0

    def test_sell_across_multiple_lots(self):
        """
        跨 Lot 賣出：賣出股數橫跨多個 Lot。
        情境：
        - Lot 1: 1000 股 @ 580
        - Lot 2: 500 股 @ 600
        - 賣出 1200 股 → Lot 1 完全賣出 + Lot 2 部分賣出 200 股
        """
        acc = FifoAccountant()
        acc.add_buy("LOT-000001", "2330", date(2024, 1, 2), 1000, 580.0)
        acc.add_buy("LOT-000002", "2330", date(2024, 1, 15), 500, 600.0)

        pnls = acc.add_sell("2330", 1200, 620.0)

        # 應產生 2 筆實現損益
        assert len(pnls) == 2

        # Lot 1 完全賣出：1000 * (620 - 580) = 40_000
        assert pnls[0].lot_id == "LOT-000001"
        assert pnls[0].sold_quantity == 1000
        assert pnls[0].realized_pnl == 40_000.0

        # Lot 2 部分賣出 200 股：200 * (620 - 600) = 4_000
        assert pnls[1].lot_id == "LOT-000002"
        assert pnls[1].sold_quantity == 200
        assert pnls[1].realized_pnl == 4_000.0

        # 剩餘 Lot 2 應有 300 股
        assert acc.get_total_quantity("2330") == 300
        remaining_lot = acc.get_lots("2330")[0]
        assert remaining_lot.remaining_quantity == 300
        # 剩餘成本 = 300_000 * (300/500) = 180_000
        assert remaining_lot.remaining_cost == 180_000.0

    def test_sell_with_loss(self):
        """賣出虧損時，實現損益應為負數。"""
        acc = FifoAccountant()
        acc.add_buy("LOT-000001", "2330", date(2024, 1, 2), 1000, 580.0)

        pnls = acc.add_sell("2330", 1000, 550.0)

        assert len(pnls) == 1
        assert pnls[0].realized_pnl == -30_000.0  # 550*1000 - 580*1000

    def test_sell_insufficient_shares_raises_error(self):
        """賣出股數超過庫存時應拋出錯誤。"""
        acc = FifoAccountant()
        acc.add_buy("LOT-000001", "2330", date(2024, 1, 2), 1000, 580.0)

        with pytest.raises(ValueError, match="Insufficient shares"):
            acc.add_sell("2330", 2000, 600.0)

        # 庫存應保持不變
        assert acc.get_total_quantity("2330") == 1000

    def test_sell_no_lots_raises_error(self):
        """無任何 Lot 時賣出應拋出錯誤。"""
        acc = FifoAccountant()

        with pytest.raises(ValueError, match="No lots available"):
            acc.add_sell("2330", 100, 600.0)

    def test_get_total_quantity(self):
        """驗證總股數查詢。"""
        acc = FifoAccountant()
        acc.add_buy("L-1", "2330", date(2024, 1, 2), 1000, 580.0)
        acc.add_buy("L-2", "2330", date(2024, 1, 15), 500, 600.0)

        assert acc.get_total_quantity("2330") == 1500

    def test_get_total_cost(self):
        """驗證總成本查詢。"""
        acc = FifoAccountant()
        acc.add_buy("L-1", "2330", date(2024, 1, 2), 1000, 580.0)
        acc.add_buy("L-2", "2330", date(2024, 1, 15), 500, 600.0)

        assert acc.get_total_cost("2330") == 880_000.0  # 580_000 + 300_000

    def test_get_avg_cost(self):
        """驗證每股平均成本查詢。"""
        acc = FifoAccountant()
        acc.add_buy("L-1", "2330", date(2024, 1, 2), 1000, 580.0)
        acc.add_buy("L-2", "2330", date(2024, 1, 15), 500, 600.0)

        # 平均成本 = 880_000 / 1500 ≈ 586.67
        assert acc.get_avg_cost("2330") == pytest.approx(880_000 / 1500)

    def test_get_avg_cost_zero_when_no_shares(self):
        """無持股時平均成本應為 0。"""
        acc = FifoAccountant()
        assert acc.get_avg_cost("2330") == 0.0

    def test_get_all_stock_ids(self):
        """驗證取得所有持股股票代號。"""
        acc = FifoAccountant()
        acc.add_buy("L-1", "2330", date(2024, 1, 2), 1000, 580.0)
        acc.add_buy("L-2", "2317", date(2024, 1, 3), 500, 100.0)

        stock_ids = acc.get_all_stock_ids()
        assert "2330" in stock_ids
        assert "2317" in stock_ids
        assert len(stock_ids) == 2

    def test_get_total_realized_pnl(self):
        """驗證總實現損益。"""
        acc = FifoAccountant()
        acc.add_buy("L-1", "2330", date(2024, 1, 2), 1000, 580.0)
        acc.add_buy("L-2", "2330", date(2024, 1, 15), 500, 600.0)

        acc.add_sell("2330", 1200, 620.0)  # 40_000 + 4_000 = 44_000

        assert acc.get_total_realized_pnl() == 44_000.0

    def test_reset(self):
        """重置應清空所有狀態。"""
        acc = FifoAccountant()
        acc.add_buy("L-1", "2330", date(2024, 1, 2), 1000, 580.0)
        acc.add_sell("2330", 500, 600.0)

        acc.reset()

        assert acc.get_total_quantity("2330") == 0
        assert acc.get_total_realized_pnl() == 0.0
        assert acc.get_all_stock_ids() == []

    def test_multiple_stocks_independent(self):
        """不同股票的 Lot 佇列應獨立運作。"""
        acc = FifoAccountant()
        acc.add_buy("L-1", "2330", date(2024, 1, 2), 1000, 580.0)
        acc.add_buy("L-2", "2317", date(2024, 1, 3), 2000, 100.0)

        # 賣出台積電不影響鴻海
        acc.add_sell("2330", 500, 600.0)

        assert acc.get_total_quantity("2330") == 500
        assert acc.get_total_quantity("2317") == 2000


# =========================================================================
# 4. PortfolioEngine 整合測試
# =========================================================================


class TestPortfolioEngine:
    """PortfolioEngine 事件驅動整合測試。"""

    @staticmethod
    def _make_buy_event(
        event_id: str,
        stock_id: str,
        event_date: date,
        quantity: int,
        price: float,
        fee: float = 0.0,
    ) -> SecurityTradeEvent:
        """建立買入事件。"""
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

    @staticmethod
    def _make_sell_event(
        event_id: str,
        stock_id: str,
        event_date: date,
        quantity: int,
        price: float,
    ) -> SecurityTradeEvent:
        """建立賣出事件。"""
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

    def test_process_single_buy(self):
        """處理單一買入事件。"""
        engine = PortfolioEngine()
        event = self._make_buy_event("EVT-00000001", "2330", date(2024, 1, 2), 1000, 580.0)

        engine.process_events([event])

        pos = engine.get_position("2330")
        assert pos["total_quantity"] == 1000
        assert pos["total_cost"] == 580_000.0
        assert pos["avg_cost"] == 580.0

    def test_process_buy_then_sell(self):
        """買入後完全賣出。"""
        engine = PortfolioEngine()
        buy = self._make_buy_event("EVT-00000001", "2330", date(2024, 1, 2), 1000, 580.0)
        sell = self._make_sell_event("EVT-00000002", "2330", date(2024, 1, 15), 1000, 600.0)

        engine.process_events([buy, sell])

        # 庫存應為 0
        pos = engine.get_position("2330")
        assert pos["total_quantity"] == 0

        # 實現損益
        summary = engine.get_realized_pnl_summary()
        assert summary["total_realized_pnl"] == 20_000.0
        assert summary["trade_count"] == 1

    def test_process_buy_then_partial_sell(self):
        """買入後部分賣出，驗證剩餘成本正確。"""
        engine = PortfolioEngine()
        buy = self._make_buy_event("EVT-00000001", "2330", date(2024, 1, 2), 1000, 580.0)
        sell = self._make_sell_event("EVT-00000002", "2330", date(2024, 1, 15), 300, 600.0)

        engine.process_events([buy, sell])

        pos = engine.get_position("2330")
        assert pos["total_quantity"] == 700
        assert pos["total_cost"] == 406_000.0  # 580_000 * 0.7
        assert pos["avg_cost"] == 580.0

        summary = engine.get_realized_pnl_summary()
        assert summary["total_realized_pnl"] == 6_000.0  # 300 * (600 - 580)

    def test_process_multiple_buys_then_sell(self):
        """
        多筆買入後跨 Lot 賣出。
        情境：
        - 1/2 買 1000 股 @ 580
        - 1/15 買 500 股 @ 600
        - 1/20 賣 1200 股 @ 620
        """
        engine = PortfolioEngine()
        events = [
            self._make_buy_event("EVT-00000001", "2330", date(2024, 1, 2), 1000, 580.0),
            self._make_buy_event("EVT-00000002", "2330", date(2024, 1, 15), 500, 600.0),
            self._make_sell_event("EVT-00000003", "2330", date(2024, 1, 20), 1200, 620.0),
        ]

        engine.process_events(events)

        # 剩餘 300 股（Lot 2 剩餘）
        pos = engine.get_position("2330")
        assert pos["total_quantity"] == 300
        assert pos["total_cost"] == 180_000.0  # 300_000 * (300/500)

        # 總實現損益 = 40_000 + 4_000 = 44_000
        summary = engine.get_realized_pnl_summary()
        assert summary["total_realized_pnl"] == 44_000.0
        assert summary["trade_count"] == 2

    def test_process_multiple_stocks(self):
        """多檔股票同時交易。"""
        engine = PortfolioEngine()
        events = [
            self._make_buy_event("EVT-00000001", "2330", date(2024, 1, 2), 1000, 580.0),
            self._make_buy_event("EVT-00000002", "2317", date(2024, 1, 3), 2000, 100.0),
            self._make_sell_event("EVT-00000003", "2330", date(2024, 1, 15), 500, 600.0),
        ]

        engine.process_events(events)

        positions = engine.get_all_positions()
        assert "2330" in positions
        assert "2317" in positions

        assert positions["2330"]["total_quantity"] == 500
        assert positions["2317"]["total_quantity"] == 2000

    def test_process_non_trade_event_ignored(self):
        """非交易事件應被忽略，不影響會計帳。"""
        from src.backend.ledger.domain_models import DividendEvent

        engine = PortfolioEngine()
        buy = self._make_buy_event("EVT-00000001", "2330", date(2024, 1, 2), 1000, 580.0)
        dividend = DividendEvent(
            event_id="EVT-00000002",
            event_date=date(2024, 7, 15),
            sequence_in_day=0,
            event_type=EventType.DIVIDEND_RECEIVE,
            cash_impact=10_000.0,
            source_ref="test:dividend",
            stock_id="2330",
            dividend_per_share=10.0,
            total_shares=1000,
        )

        engine.process_events([buy, dividend])

        # 股利事件不應影響持股
        pos = engine.get_position("2330")
        assert pos["total_quantity"] == 1000
        assert pos["total_cost"] == 580_000.0

    def test_reset_engine(self):
        """重置引擎應清空所有狀態。"""
        engine = PortfolioEngine()
        buy = self._make_buy_event("EVT-00000001", "2330", date(2024, 1, 2), 1000, 580.0)
        engine.process_events([buy])

        engine.reset()

        assert engine.get_all_positions() == {}
        summary = engine.get_realized_pnl_summary()
        assert summary["total_realized_pnl"] == 0.0
        assert summary["trade_count"] == 0

    def test_sell_without_buy_raises_error(self):
        """未買入就賣出應拋出錯誤。"""
        engine = PortfolioEngine()
        sell = self._make_sell_event("EVT-00000001", "2330", date(2024, 1, 15), 1000, 600.0)

        with pytest.raises(ValueError, match="No lots available"):
            engine.process_events([sell])

    def test_sell_excess_shares_raises_error(self):
        """賣出超過庫存股數應拋出錯誤。"""
        engine = PortfolioEngine()
        buy = self._make_buy_event("EVT-00000001", "2330", date(2024, 1, 2), 1000, 580.0)
        sell = self._make_sell_event("EVT-00000002", "2330", date(2024, 1, 15), 2000, 600.0)

        with pytest.raises(ValueError, match="Insufficient shares"):
            engine.process_events([buy, sell])
