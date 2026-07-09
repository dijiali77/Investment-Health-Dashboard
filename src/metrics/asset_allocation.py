"""
資產配置比例（Asset Allocation）算子

計算各檔標的在投資組合中的即時市值權重（%）。
"""

from datetime import date
from typing import Dict, List, Optional

import pandas as pd

from src.portfolio import PortfolioEngine
from src.market_data.locf_operator import apply_locf


class AssetAllocationCalculator:
    """
    資產配置比例計算器。

    給定 PortfolioEngine 的持股狀態與市場價格資料，
    計算各檔股票在投資組合中的市值權重。

    Attributes
    ----------
    engine : PortfolioEngine
        已處理過事件的 PortfolioEngine 實例。
    """

    def __init__(self, engine: PortfolioEngine):
        self.engine = engine

    def calculate(
        self,
        market_data: Dict[str, pd.DataFrame],
        target_date: Optional[date] = None,
        *,
        date_col: str = "date",
        price_col: str = "adj_close",
    ) -> Dict:
        """
        計算指定日期的資產配置比例。

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
            - allocations: List[Dict]，各標的的配置明細（按權重降序排列）
            - total_market_value: float，總市值
            - cash_equivalent: float，現金等價物（目前為 0，待 Phase 5 整合）
            - calculation_date: date 或 None
        """
        positions = {}
        total_market_value = 0.0

        for stock_id in self.engine.accountant.get_all_stock_ids():
            lots = self.engine.accountant.get_lots(stock_id)
            total_qty = sum(lot.remaining_quantity for lot in lots)

            if total_qty <= 0:
                continue

            # 取得價格
            price = self._get_price(
                stock_id=stock_id,
                market_data=market_data.get(stock_id),
                target_date=target_date,
                date_col=date_col,
                price_col=price_col,
            )

            if price is None:
                continue

            market_value = total_qty * price
            positions[stock_id] = {
                "stock_id": stock_id,
                "quantity": total_qty,
                "price": round(price, 2),
                "market_value": round(market_value, 2),
            }
            total_market_value += market_value

        # 計算權重並排序（降序）
        allocations = []
        for stock_id, pos in positions.items():
            weight_pct = (
                round((pos["market_value"] / total_market_value) * 100, 2)
                if total_market_value > 0
                else 0.0
            )
            allocations.append(
                {
                    "stock_id": stock_id,
                    "quantity": pos["quantity"],
                    "price": pos["price"],
                    "market_value": pos["market_value"],
                    "weight_pct": weight_pct,
                }
            )

        allocations.sort(key=lambda x: x["weight_pct"], reverse=True)

        return {
            "allocations": allocations,
            "total_market_value": round(total_market_value, 2),
            "cash_equivalent": 0.0,
            "calculation_date": target_date,
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
            try:
                filled = apply_locf(
                    market_data,
                    date_col=date_col,
                    price_col=price_col,
                )
                mask = filled[date_col] <= target_date
                if not mask.any():
                    return None
                return float(filled[mask].iloc[-1][price_col])
            except (ValueError, IndexError, KeyError):
                return None
        else:
            sorted_df = market_data.sort_values(date_col)
            return float(sorted_df[price_col].iloc[-1])

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
        計算指定時間區間內每日的資產配置時間序列。

        Returns
        -------
        pd.DataFrame
            每日各股票的權重，欄位為 stock_id，值為權重百分比。
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
            record = {"date": calc_date}
            for alloc in result["allocations"]:
                record[alloc["stock_id"]] = alloc["weight_pct"]
            records.append(record)

        return pd.DataFrame(records).set_index("date")
