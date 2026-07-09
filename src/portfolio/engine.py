"""
Portfolio Engine（投資組合引擎）

接收已排序的 FinancialEvent 序列，驅動 FIFO 會計帳，
維護各股票的持倉狀態、實現損益記錄，以及雙階段股利會計。

支援的股利會計邏輯：
1. 第一階段（除權息日）：根據持股 Lots 計算應收股利，建立 DividendReceivable
2. 第二階段（發放日）：將 DividendReceivable 銷帳，增加現金餘額
"""

from datetime import date
from typing import Dict, List, Optional, Tuple

from src.ledger.domain_models import (
    FinancialEvent,
    SecurityTradeEvent,
    DividendEvent,
    EventType,
)
from src.accounting import DividendReceivable
from .lot import Lot, RealizedPnL
from .fifo_accountant import FifoAccountant


class PortfolioEngine:
    """
    投資組合引擎。

    接收已排序的 FinancialEvent 序列，依序處理買賣事件與股利事件，
    更新 FIFO 會計帳的 Lot 佇列、實現損益，以及應收股利追蹤。

    Attributes
    ----------
    accountant : FifoAccountant
        FIFO 會計帳實例。
    dividend_receivables : List[DividendReceivable]
        所有應收股利記錄（含已銷帳與未銷帳）。
    """

    def __init__(self):
        self.accountant = FifoAccountant()
        self.dividend_receivables: List[DividendReceivable] = []
        self._lot_counter: int = 0

    # ── 事件處理 ────────────────────────────────────────────────

    def process_events(self, events: List[FinancialEvent]) -> None:
        """
        處理一組已排序的 FinancialEvent 序列。

        支援的事件類型：
        - SecurityTradeEvent（BUY/SELL）：更新 FIFO 會計帳
        - DividendEvent：雙階段股利會計
          - 若 event_date == ex_dividend_date：第一階段，產生應收股利
          - 若 event_date == payment_date（且 ≠ ex_dividend_date）：第二階段，銷帳

        Parameters
        ----------
        events : List[FinancialEvent]
            已按 (event_date, sequence_in_day, event_id) 排序的事件列表。
        """
        for event in events:
            self._process_single_event(event)

    def _process_single_event(self, event: FinancialEvent) -> None:
        """處理單一事件。"""
        if isinstance(event, SecurityTradeEvent):
            if event.event_type == EventType.SECURITY_BUY:
                self._handle_buy(event)
            elif event.event_type == EventType.SECURITY_SELL:
                self._handle_sell(event)
        elif isinstance(event, DividendEvent):
            self._handle_dividend(event)
        # 其他事件類型（StockDividendEvent, CorporateActionEvent 等）暫不處理

    def _handle_dividend(self, event: DividendEvent) -> Optional[DividendReceivable]:
        """
        處理股利事件的雙階段會計邏輯。

        第一階段（除權息日）：
        - 若 event.event_date == event.ex_dividend_date（或 ex_dividend_date 為 None）
        - 根據當日持股 Lots 計算應收股利
        - 建立 DividendReceivable 加入追蹤列表

        第二階段（發放日）：
        - 若 event.event_date > event.ex_dividend_date（且 ex_dividend_date 不為 None）
        - 尋找對應的未銷帳 DividendReceivable
        - 將其標記為已銷帳（is_settled=True）

        Parameters
        ----------
        event : DividendEvent
            股利事件。

        Returns
        -------
        Optional[DividendReceivable]
            若為第一階段，回傳新建立的 DividendReceivable；
            若為第二階段，回傳已銷帳的 DividendReceivable；
            若無法處理，回傳 None。
        """
        # 判斷階段：若 event_date 與 ex_dividend_date 相同（或無 ex_dividend_date），
        # 視為第一階段（除權息日）
        is_first_stage = (
            event.ex_dividend_date is None
            or event.event_date == event.ex_dividend_date
        )

        if is_first_stage:
            return self._handle_dividend_stage1(event)
        else:
            return self._handle_dividend_stage2(event)

    def _handle_dividend_stage1(
        self, event: DividendEvent
    ) -> Optional[DividendReceivable]:
        """
        第一階段：除權息日，產生應收股利。

        根據當日持股 Lots 計算應收股利總額。
        若無持股，則不產生應收股利。
        """
        total_shares = self.accountant.get_total_quantity(event.stock_id)
        if total_shares <= 0:
            return None

        gross_amount = total_shares * event.dividend_per_share
        net_amount = round(gross_amount - event.withholding_tax, 2)

        receivable = DividendReceivable(
            receivable_id=f"DR-{event.event_id}",
            stock_id=event.stock_id,
            ex_dividend_date=event.event_date,
            payment_date=event.event_date,  # 預設與除權息日相同，可後續更新
            total_shares=total_shares,
            dividend_per_share=event.dividend_per_share,
            gross_amount=gross_amount,
            withholding_tax=event.withholding_tax,
            net_amount=net_amount,
            is_settled=False,
        )
        self.dividend_receivables.append(receivable)
        return receivable

    def _handle_dividend_stage2(
        self, event: DividendEvent
    ) -> Optional[DividendReceivable]:
        """
        第二階段：發放日，銷帳應收股利。

        尋找對應的未銷帳 DividendReceivable（依 stock_id 與 ex_dividend_date 匹配），
        將其標記為已銷帳。
        """
        for i, dr in enumerate(self.dividend_receivables):
            if (
                dr.stock_id == event.stock_id
                and dr.ex_dividend_date == event.ex_dividend_date
                and not dr.is_settled
            ):
                settled = dr.settle()
                # 更新 payment_date 為實際發放日
                settled_dr = DividendReceivable(
                    receivable_id=settled.receivable_id,
                    stock_id=settled.stock_id,
                    ex_dividend_date=settled.ex_dividend_date,
                    payment_date=event.event_date,
                    total_shares=settled.total_shares,
                    dividend_per_share=settled.dividend_per_share,
                    gross_amount=settled.gross_amount,
                    withholding_tax=settled.withholding_tax,
                    net_amount=settled.net_amount,
                    is_settled=True,
                )
                self.dividend_receivables[i] = settled_dr
                return settled_dr

        return None

    def _handle_buy(self, event: SecurityTradeEvent) -> Lot:
        """處理買入事件。"""
        self._lot_counter += 1
        lot_id = f"LOT-{self._lot_counter:06d}"
        return self.accountant.add_buy(
            lot_id=lot_id,
            stock_id=event.stock_id,
            buy_date=event.event_date,
            quantity=event.quantity,
            price=event.price,
            fee=event.fee,
        )

    def _handle_sell(self, event: SecurityTradeEvent) -> List[RealizedPnL]:
        """處理賣出事件。"""
        return self.accountant.add_sell(
            stock_id=event.stock_id,
            sell_quantity=event.quantity,
            sell_price=event.price,
        )

    # ── 查詢介面 ────────────────────────────────────────────────

    def get_position(self, stock_id: str) -> Dict:
        """
        取得指定股票的持倉摘要。

        Parameters
        ----------
        stock_id : str
            股票代號。

        Returns
        -------
        Dict
            包含以下鍵值：
            - stock_id: 股票代號
            - total_quantity: 總持有股數
            - total_cost: 總持有成本
            - avg_cost: 每股平均成本
            - lots: Lot 列表
        """
        return {
            "stock_id": stock_id,
            "total_quantity": self.accountant.get_total_quantity(stock_id),
            "total_cost": self.accountant.get_total_cost(stock_id),
            "avg_cost": self.accountant.get_avg_cost(stock_id),
            "lots": self.accountant.get_lots(stock_id),
        }

    def get_all_positions(self) -> Dict[str, Dict]:
        """
        取得所有持股的持倉摘要。

        Returns
        -------
        Dict[str, Dict]
            key 為 stock_id，value 為持倉摘要。
        """
        return {
            sid: self.get_position(sid)
            for sid in self.accountant.get_all_stock_ids()
        }

    def get_realized_pnl_summary(self) -> Dict:
        """
        取得已實現損益摘要。

        Returns
        -------
        Dict
            包含以下鍵值：
            - total_realized_pnl: 總實現損益
            - trade_count: 交易次數
            - details: 所有實現損益明細
        """
        return {
            "total_realized_pnl": self.accountant.get_total_realized_pnl(),
            "trade_count": len(self.accountant.realized_pnls),
            "details": list(self.accountant.realized_pnls),
        }

    def reset(self) -> None:
        """重置引擎狀態。"""
        self.accountant.reset()
        self.dividend_receivables.clear()
        self._lot_counter = 0
