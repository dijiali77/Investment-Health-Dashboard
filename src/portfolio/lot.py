"""
Lot（持股批次）資料模型

代表一筆買入所建立的持股批次，用於 FIFO 會計帳的銷帳與成本計算。
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class Lot:
    """
    單一持股批次。

    每當發生一筆買入（SecurityTradeEvent with BUY），
    Portfolio Engine 即建立一個 Lot 加入 FIFO 佇列。

    Attributes
    ----------
    lot_id : str
        唯一批次編號，格式 LOT-{event_id}。
    stock_id : str
        股票代號。
    buy_date : date
        買入日期（成交日）。
    total_quantity : int
        原始買入股數。
    remaining_quantity : int
        尚未賣出的剩餘股數。
    total_cost : float
        原始買入總成本（含手續費）。
    remaining_cost : float
        剩餘股數對應的成本（按比例分攤）。
    buy_price : float
        原始買入價格（每股）。
    """
    lot_id: str
    stock_id: str
    buy_date: date
    total_quantity: int
    remaining_quantity: int
    total_cost: float
    remaining_cost: float
    buy_price: float

    @property
    def is_closed(self) -> bool:
        """此 Lot 是否已完全賣出。"""
        return self.remaining_quantity <= 0

    @property
    def avg_cost_per_share(self) -> float:
        """
        剩餘股數的每股平均成本。
        若剩餘股數為 0，回傳 0.0。
        """
        if self.remaining_quantity <= 0:
            return 0.0
        return self.remaining_cost / self.remaining_quantity

    def dilute(self, sold_quantity: int, sold_price: float) -> "RealizedPnL":
        """
        從此 Lot 中賣出指定股數，回傳實現損益。

        採用 FIFO 原則：先買入的 Lot 先被賣出。
        若 sold_quantity > remaining_quantity，則只賣出剩餘股數。

        Parameters
        ----------
        sold_quantity : int
            欲賣出的股數。
        sold_price : float
            賣出價格（每股）。

        Returns
        -------
        RealizedPnL
            本次賣出的實現損益明細。
        """
        actual_sold = min(sold_quantity, self.remaining_quantity)
        if actual_sold <= 0:
            return RealizedPnL(
                lot_id=self.lot_id,
                sold_quantity=0,
                sold_price=sold_price,
                cost_basis=0.0,
                realized_pnl=0.0,
            )

        # 按比例計算賣出部分的成本基礎
        cost_ratio = actual_sold / self.total_quantity
        cost_basis = self.total_cost * cost_ratio

        # 賣出收入（不含手續費/稅，由外部計算）
        proceeds = actual_sold * sold_price
        realized_pnl = proceeds - cost_basis

        return RealizedPnL(
            lot_id=self.lot_id,
            sold_quantity=actual_sold,
            sold_price=sold_price,
            cost_basis=cost_basis,
            realized_pnl=realized_pnl,
        )

    def apply_dilution(self, ratio: float) -> "Lot":
        """
        套用稀釋（股票股利/分割/合併），回傳新的 Lot。

        不修改原 Lot（frozen=True），而是回傳新的 Lot 實例。
        ratio 定義：
        - 股票股利每股配 0.2 股 → ratio = 1.2
        - 2:1 分割 → ratio = 2.0
        - 1:2 合併 → ratio = 0.5

        Parameters
        ----------
        ratio : float
            稀釋比率。

        Returns
        -------
        Lot
            稀釋後的 Lot。
        """
        new_qty = round(self.remaining_quantity * ratio)
        new_total_qty = round(self.total_quantity * ratio)
        # 成本不變，但每股成本會改變
        return Lot(
            lot_id=self.lot_id,
            stock_id=self.stock_id,
            buy_date=self.buy_date,
            total_quantity=new_total_qty,
            remaining_quantity=new_qty,
            total_cost=self.total_cost,
            remaining_cost=self.remaining_cost,
            buy_price=self.total_cost / new_total_qty if new_total_qty > 0 else 0.0,
        )


@dataclass(frozen=True)
class RealizedPnL:
    """
    單筆賣出的實現損益明細。

    Attributes
    ----------
    lot_id : str
        來源 Lot 編號。
    sold_quantity : int
        本次賣出股數。
    sold_price : float
        賣出價格（每股）。
    cost_basis : float
        賣出部分的成本基礎。
    realized_pnl : float
        實現損益（正數為獲利，負數為虧損）。
    """
    lot_id: str
    sold_quantity: int
    sold_price: float
    cost_basis: float
    realized_pnl: float
