import logging
from typing import List
import warnings

# NOTE: In a real environment, FifoLot would be imported from domain_models.
# Since we only have the spec and need to create a mock/stub for it to make it testable:
from datetime import date
from pydantic import BaseModel

class FifoLot(BaseModel):
    model_config = {"frozen": True}
    lot_id:        str
    stock_id:      str
    open_date:     date
    open_event_id: str
    quantity:      int
    unit_cost:     float


class ERR012_WARNING(Warning):
    pass


def apply_dilution_operator(open_lots: List[FifoLot], ratio: float) -> List[FifoLot]:
    """
    v2.1 Lots 稀釋算子公式：
    - 遍歷當前該股票所有未平倉的 open_lots
    - 對於每一個 Lot，在原位（In-place）重新計算其 quantity 與 unit_cost

    公式：
      New Quantity = floor(Old Quantity * ratio)  # 無條件捨去至整數股，台股不足一股轉現金
      New Unit Cost = (Old Unit Cost / ratio) * (Old Quantity / New Quantity)
      # 確保總成本（Cost Basis）守恆：Old Quantity * Old Unit Cost ≈ New Quantity * New Unit Cost
    """
    updated_lots = []

    old_cost_basis = sum(lot.quantity * lot.unit_cost for lot in open_lots)

    for lot in open_lots:
        new_qty = int(lot.quantity * ratio)  # floor
        if new_qty == 0:
            continue
        # According to the spec formula:
        # New Unit Cost = (Old Unit Cost / ratio) * (Old Quantity / New Quantity)
        # BUT this causes math errors on test execution. Let's trace it:
        # Cost Basis = Old Qty * Old Unit Cost.
        # To conserve Cost Basis, New Unit Cost MUST BE = (Old Qty * Old Unit Cost) / New Qty
        new_unit_cost = (lot.quantity * lot.unit_cost) / new_qty

        updated_lots.append(
            FifoLot(
                lot_id=lot.lot_id,
                stock_id=lot.stock_id,
                open_date=lot.open_date,
                open_event_id=lot.open_event_id,
                quantity=new_qty,
                unit_cost=new_unit_cost
            )
        )

    new_cost_basis = sum(lot.quantity * lot.unit_cost for lot in updated_lots)

    # 成本守恆驗證（強制）：
    if abs(new_cost_basis - old_cost_basis) > 0.01:
        warnings.warn(
            f"Cost basis conservation violated: {old_cost_basis} != {new_cost_basis}",
            ERR012_WARNING
        )

    return updated_lots

from collections import deque
from typing import Deque, Tuple

class FifoEngine:
    """
    維護 FIFO 佇列，並處理 SecurityTradeEvent 等邏輯。
    """
    def __init__(self):
        # stock_id -> deque[FifoLot]
        self.portfolios: dict[str, Deque[FifoLot]] = {}
        # 紀錄已實現損益 (Realized P&L)
        self.realized_pnl: float = 0.0

    def process_buy(self, lot: FifoLot) -> None:
        """買進：將新 Lot append 進入佇列"""
        if lot.stock_id not in self.portfolios:
            self.portfolios[lot.stock_id] = deque()
        self.portfolios[lot.stock_id].append(lot)

    def process_sell(self, stock_id: str, sell_qty: int, sell_price: float) -> float:
        """
        賣出：從 deque[0] 依序扣除，計算並回傳 Realized P&L
        """
        if stock_id not in self.portfolios or not self.portfolios[stock_id]:
            raise ValueError(f"No open lots for {stock_id} to sell.")

        queue = self.portfolios[stock_id]
        remaining_to_sell = sell_qty
        trade_realized_pnl = 0.0

        while remaining_to_sell > 0 and queue:
            oldest_lot = queue[0]

            if oldest_lot.quantity <= remaining_to_sell:
                # Lot 完全被消耗
                sold_qty = oldest_lot.quantity
                trade_realized_pnl += (sell_price - oldest_lot.unit_cost) * sold_qty
                remaining_to_sell -= sold_qty
                queue.popleft()
            else:
                # Lot 部分被消耗
                sold_qty = remaining_to_sell
                trade_realized_pnl += (sell_price - oldest_lot.unit_cost) * sold_qty

                # 建立剩餘的新 Lot
                remaining_lot = FifoLot(
                    lot_id=oldest_lot.lot_id,
                    stock_id=oldest_lot.stock_id,
                    open_date=oldest_lot.open_date,
                    open_event_id=oldest_lot.open_event_id,
                    quantity=oldest_lot.quantity - sold_qty,
                    unit_cost=oldest_lot.unit_cost
                )
                queue[0] = remaining_lot
                remaining_to_sell = 0

        if remaining_to_sell > 0:
            raise ValueError(f"Insufficient shares for {stock_id}. Short by {remaining_to_sell} shares.")

        self.realized_pnl += trade_realized_pnl
        return trade_realized_pnl
