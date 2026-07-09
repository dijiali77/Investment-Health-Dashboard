"""
Portfolio Engine（投資組合引擎）

接收已排序的 FinancialEvent 序列，驅動 FIFO 會計帳，
維護各股票的持倉狀態與實現損益記錄。
"""

from datetime import date
from typing import Dict, List, Optional, Tuple

from src.backend.ledger.domain_models import (
    FinancialEvent,
    SecurityTradeEvent,
    EventType,
)
from .lot import Lot, RealizedPnL
from .fifo_accountant import FifoAccountant


class PortfolioEngine:
    """
    投資組合引擎。

    接收已排序的 FinancialEvent 序列，依序處理買賣事件，
    更新 FIFO 會計帳的 Lot 佇列與實現損益。

    Attributes
    ----------
    accountant : FifoAccountant
        FIFO 會計帳實例。
    """

    def __init__(self):
        self.accountant = FifoAccountant()
        self._lot_counter: int = 0

    # ── 事件處理 ────────────────────────────────────────────────

    def process_events(self, events: List[FinancialEvent]) -> None:
        """
        處理一組已排序的 FinancialEvent 序列。

        僅處理 SecurityTradeEvent（BUY/SELL），
        其他事件類型（股利、公司行動等）暫不處理。

        Parameters
        ----------
        events : List[FinancialEvent]
            已按 (event_date, sequence_in_day, event_id) 排序的事件列表。

        Raises
        ------
        ValueError
            若事件序列未排序（由外部確保，此處不重複驗證）。
        """
        for event in events:
            self._process_single_event(event)

    def _process_single_event(self, event: FinancialEvent) -> None:
        """處理單一事件。"""
        if not isinstance(event, SecurityTradeEvent):
            return  # 非交易事件暫不處理

        if event.event_type == EventType.SECURITY_BUY:
            self._handle_buy(event)
        elif event.event_type == EventType.SECURITY_SELL:
            self._handle_sell(event)

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
        self._lot_counter = 0
