"""
FIFO（先進先出）會計帳算子

管理各股票的持股批次（Lot）佇列，處理買入建 Lot、賣出銷 Lot、
部分賣出稀釋等操作，並計算實現損益。
"""

from collections import deque, defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from .lot import Lot, RealizedPnL


class FifoAccountant:
    """
    FIFO 會計帳。

    為每檔股票維護一個 Lot 佇列（先進先出），
    賣出時從最早的 Lot 開始銷帳。

    Attributes
    ----------
    lots : Dict[str, deque[Lot]]
        各股票的 Lot 佇列，key 為 stock_id。
    realized_pnls : List[RealizedPnL]
        所有已實現損益的歷史記錄。
    """

    def __init__(self):
        self.lots: Dict[str, deque[Lot]] = defaultdict(deque)
        self.realized_pnls: List[RealizedPnL] = []

    # ── 買入 ────────────────────────────────────────────────────

    def add_buy(
        self,
        lot_id: str,
        stock_id: str,
        buy_date: date,
        quantity: int,
        price: float,
        fee: float = 0.0,
    ) -> Lot:
        """
        記錄一筆買入，建立新的 Lot 並加入 FIFO 佇列尾端。

        Parameters
        ----------
        lot_id : str
            批次編號。
        stock_id : str
            股票代號。
        buy_date : date
            買入日期。
        quantity : int
            買入股數。
        price : float
            買入價格（每股）。
        fee : float
            手續費。

        Returns
        -------
        Lot
            新建立的 Lot。
        """
        total_cost = quantity * price + fee
        lot = Lot(
            lot_id=lot_id,
            stock_id=stock_id,
            buy_date=buy_date,
            total_quantity=quantity,
            remaining_quantity=quantity,
            total_cost=total_cost,
            remaining_cost=total_cost,
            buy_price=price,
        )
        self.lots[stock_id].append(lot)
        return lot

    # ── 賣出 ────────────────────────────────────────────────────

    def add_sell(
        self,
        stock_id: str,
        sell_quantity: int,
        sell_price: float,
    ) -> List[RealizedPnL]:
        """
        記錄一筆賣出，從 FIFO 佇列前端開始銷帳。

        若賣出股數跨越多個 Lot，會依序從最早的 Lot 開始扣除，
        直到賣出股數滿足為止。每個被部分或完全銷帳的 Lot
        都會產生對應的 RealizedPnL。

        Parameters
        ----------
        stock_id : str
            股票代號。
        sell_quantity : int
            賣出股數。
        sell_price : float
            賣出價格（每股）。

        Returns
        -------
        List[RealizedPnL]
            本次賣出產生的實現損益明細列表（可能跨多個 Lot）。

        Raises
        ------
        ValueError
            若該股票無任何 Lot 可銷帳。
        ValueError
            若賣出股數大於總持有股數（庫存不足）。
        """
        if stock_id not in self.lots or not self.lots[stock_id]:
            raise ValueError(
                f"No lots available for stock '{stock_id}' to sell"
            )

        total_available = sum(
            lot.remaining_quantity for lot in self.lots[stock_id]
        )
        if sell_quantity > total_available:
            raise ValueError(
                f"Insufficient shares for stock '{stock_id}': "
                f"requested {sell_quantity}, available {total_available}"
            )

        remaining_to_sell = sell_quantity
        pnl_records: List[RealizedPnL] = []

        while remaining_to_sell > 0 and self.lots[stock_id]:
            oldest_lot = self.lots[stock_id][0]

            # 計算本次從此 Lot 賣出的股數
            sell_from_lot = min(remaining_to_sell, oldest_lot.remaining_quantity)

            # 計算實現損益
            pnl = oldest_lot.dilute(sell_from_lot, sell_price)
            pnl_records.append(pnl)
            self.realized_pnls.append(pnl)

            # 更新 Lot 的剩餘股數與成本
            cost_ratio = sell_from_lot / oldest_lot.total_quantity
            new_remaining_qty = oldest_lot.remaining_quantity - sell_from_lot
            new_remaining_cost = oldest_lot.remaining_cost - (
                oldest_lot.total_cost * cost_ratio
            )

            # 建立更新後的 Lot（frozen=True，所以建立新實例）
            updated_lot = Lot(
                lot_id=oldest_lot.lot_id,
                stock_id=oldest_lot.stock_id,
                buy_date=oldest_lot.buy_date,
                total_quantity=oldest_lot.total_quantity,
                remaining_quantity=new_remaining_qty,
                total_cost=oldest_lot.total_cost,
                remaining_cost=round(new_remaining_cost, 4),
                buy_price=oldest_lot.buy_price,
            )

            # 取代佇列前端
            self.lots[stock_id].popleft()
            if new_remaining_qty > 0:
                self.lots[stock_id].appendleft(updated_lot)

            remaining_to_sell -= sell_from_lot

        return pnl_records

    # ── 查詢 ────────────────────────────────────────────────────

    def get_lots(self, stock_id: str) -> List[Lot]:
        """
        取得指定股票的所有 Lot（按買入日期排序）。

        Parameters
        ----------
        stock_id : str
            股票代號。

        Returns
        -------
        List[Lot]
            Lot 列表，由舊到新排序。
        """
        return list(self.lots.get(stock_id, []))

    def get_total_quantity(self, stock_id: str) -> int:
        """
        取得指定股票的總持有股數。

        Parameters
        ----------
        stock_id : str
            股票代號。

        Returns
        -------
        int
            總持有股數。
        """
        return sum(
            lot.remaining_quantity for lot in self.lots.get(stock_id, [])
        )

    def get_total_cost(self, stock_id: str) -> float:
        """
        取得指定股票的總持有成本。

        Parameters
        ----------
        stock_id : str
            股票代號。

        Returns
        -------
        float
            總持有成本。
        """
        return sum(
            lot.remaining_cost for lot in self.lots.get(stock_id, [])
        )

    def get_avg_cost(self, stock_id: str) -> float:
        """
        取得指定股票的每股平均成本。

        Parameters
        ----------
        stock_id : str
            股票代號。

        Returns
        -------
        float
            每股平均成本。若無持股，回傳 0.0。
        """
        total_qty = self.get_total_quantity(stock_id)
        if total_qty <= 0:
            return 0.0
        return self.get_total_cost(stock_id) / total_qty

    def get_all_stock_ids(self) -> List[str]:
        """
        取得所有有持股的股票代號列表。

        Returns
        -------
        List[str]
            股票代號列表。
        """
        return [
            sid for sid, lots in self.lots.items()
            if any(lot.remaining_quantity > 0 for lot in lots)
        ]

    def get_total_realized_pnl(self) -> float:
        """
        取得所有已實現損益的總和。

        Returns
        -------
        float
            總實現損益。
        """
        return sum(pnl.realized_pnl for pnl in self.realized_pnls)

    def reset(self) -> None:
        """重置所有狀態（清空 Lot 佇列與損益記錄）。"""
        self.lots.clear()
        self.realized_pnls.clear()
