"""
未實現損益（Unrealized PnL）算子

結合 PortfolioEngine 當前的持股 Lot 與 Market Data 的最新/特定日期收盤價，
計算即時的帳面損益。
"""

from datetime import date
from typing import Dict, List, Optional

import pandas as pd

from src.backend.portfolio_engine import Lot, PortfolioEngine
from src.backend.market_data.locf_operator import apply_locf


class UnrealizedPnlCalculator:
    """
    未實現損益計算器。

    給定 PortfolioEngine 的持股狀態與市場價格資料，
    計算各檔股票與整體投資組合的未實現損益。

    Attributes
    ----------
    engine : PortfolioEngine
        已處理過事件的 PortfolioEngine 實例。
    """

    def __init__(self, engine: PortfolioEngine):
        self.engine = engine

    # ── 單一日期計算 ────────────────────────────────────────────

    def calculate(
        self,
        market_data: Dict[str, pd.DataFrame],
        target_date: Optional[date] = None,
        *,
        date_col: str = "date",
        price_col: str = "adj_close",
    ) -> Dict:
        """
        計算指定日期的未實現損益。

        若未指定 target_date，則使用各股票最後可得的價格。
        若指定 target_date，則透過 apply_locf 補值到該日期。

        Parameters
        ----------
        market_data : Dict[str, pd.DataFrame]
            key 為 stock_id，value 為包含 date_col 與 price_col 的 DataFrame。
        target_date : Optional[date], default None
            目標計算日期。若為 None，使用各股票最後一筆價格。
        date_col : str, default "date"
            市場資料的日期欄位名稱。
        price_col : str, default "adj_close"
            市場資料的價格欄位名稱。

        Returns
        -------
        Dict
            包含以下鍵值：
            - positions: Dict[str, Dict]，各股票的未實現損益明細
            - total_unrealized_pnl: float，總未實現損益
            - total_market_value: float，總市值
            - total_cost: float，總持有成本
            - calculation_date: date 或 None
        """
        positions = {}
        total_market_value = 0.0
        total_cost = 0.0

        for stock_id in self.engine.accountant.get_all_stock_ids():
            pos = self._calc_single_stock(
                stock_id=stock_id,
                market_data=market_data.get(stock_id),
                target_date=target_date,
                date_col=date_col,
                price_col=price_col,
            )
            if pos is not None:
                positions[stock_id] = pos
                total_market_value += pos["market_value"]
                total_cost += pos["cost_basis"]

        total_unrealized_pnl = total_market_value - total_cost

        return {
            "positions": positions,
            "total_unrealized_pnl": round(total_unrealized_pnl, 2),
            "total_market_value": round(total_market_value, 2),
            "total_cost": round(total_cost, 2),
            "calculation_date": target_date,
        }

    def _calc_single_stock(
        self,
        stock_id: str,
        market_data: Optional[pd.DataFrame],
        target_date: Optional[date],
        date_col: str,
        price_col: str,
    ) -> Optional[Dict]:
        """計算單一股票的未實現損益。"""
        lots = self.engine.accountant.get_lots(stock_id)
        total_qty = sum(lot.remaining_quantity for lot in lots)
        total_cost = sum(lot.remaining_cost for lot in lots)

        if total_qty <= 0:
            return None

        # 取得價格
        price = self._get_price(
            stock_id=stock_id,
            market_data=market_data,
            target_date=target_date,
            date_col=date_col,
            price_col=price_col,
        )

        if price is None:
            return None

        market_value = total_qty * price
        unrealized_pnl = market_value - total_cost
        unrealized_pnl_pct = (
            (unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0
        )

        return {
            "stock_id": stock_id,
            "quantity": total_qty,
            "avg_cost": round(total_cost / total_qty, 2),
            "current_price": round(price, 2),
            "cost_basis": round(total_cost, 2),
            "market_value": round(market_value, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
            "lots": [
                {
                    "lot_id": lot.lot_id,
                    "remaining_qty": lot.remaining_quantity,
                    "avg_cost": round(lot.avg_cost_per_share, 2),
                    "remaining_cost": round(lot.remaining_cost, 2),
                }
                for lot in lots
            ],
        }

    def _get_price(
        self,
        stock_id: str,
        market_data: Optional[pd.DataFrame],
        target_date: Optional[date],
        date_col: str,
        price_col: str,
    ) -> Optional[float]:
        """取得指定日期的價格。"""
        if market_data is None or market_data.empty:
            return None

        if target_date is not None:
            # 使用 LOCF 補值到目標日期
            try:
                filled = apply_locf(
                    market_data,
                    date_col=date_col,
                    price_col=price_col,
                )
                # 找到目標日期或之前的最後一個價格
                mask = filled[date_col] <= target_date
                if not mask.any():
                    return None
                last_row = filled[mask].iloc[-1]
                return float(last_row[price_col])
            except (ValueError, IndexError, KeyError):
                return None
        else:
            # 使用最後一筆價格
            sorted_df = market_data.sort_values(date_col)
            return float(sorted_df[price_col].iloc[-1])

    # ── 多日期時間序列計算 ──────────────────────────────────────

    def calculate_time_series(
        self,
        market_data: Dict[str, pd.DataFrame],
        start_date: date,
        end_date: date,
        *,
        date_col: str = "date",
        price_col: str = "adj_close",
    ) -> pd.DataFrame:
        """
        計算指定時間區間內每日的未實現損益時間序列。

        Parameters
        ----------
        market_data : Dict[str, pd.DataFrame]
            key 為 stock_id，value 為市場資料 DataFrame。
        start_date : date
            起始日期（含）。
        end_date : date
            結束日期（含）。
        date_col : str, default "date"
            市場資料的日期欄位名稱。
        price_col : str, default "adj_close"
            市場資料的價格欄位名稱。

        Returns
        -------
        pd.DataFrame
            包含每日未實現損益的 DataFrame，欄位：
            - date: 日期
            - total_market_value: 總市值
            - total_cost: 總成本
            - unrealized_pnl: 未實現損益
            - unrealized_pnl_pct: 未實現損益百分比
        """
        date_range = pd.date_range(start=start_date, end=end_date, freq="D")
        records = []

        for d in date_range:
            calc_date = d.date()
            result = self.calculate(
                market_data=market_data,
                target_date=calc_date,
                date_col=date_col,
                price_col=price_col,
            )
            records.append(
                {
                    "date": calc_date,
                    "total_market_value": result["total_market_value"],
                    "total_cost": result["total_cost"],
                    "unrealized_pnl": result["total_unrealized_pnl"],
                    "unrealized_pnl_pct": (
                        round(
                            result["total_unrealized_pnl"]
                            / result["total_cost"]
                            * 100,
                            2,
                        )
                        if result["total_cost"] > 0
                        else 0.0
                    ),
                }
            )

        return pd.DataFrame(records).set_index("date")
