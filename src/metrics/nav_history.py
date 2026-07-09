"""
投資組合歷史淨值（Portfolio NAV History）序列生成

給定時間區間，結合歷史事件與每日市場價格，
產出每日的總市值、總資產淨值曲線數據。
"""

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

from src.ledger.domain_models import (
    FinancialEvent,
    SecurityTradeEvent,
    DividendEvent,
    EventType,
)
from src.portfolio import PortfolioEngine
from src.accounting import DividendReceivable
from src.market_data.locf_operator import apply_locf


class NavHistoryGenerator:
    """
    投資組合歷史淨值序列生成器。

    給定時間區間，逐步回放事件並結合每日市場價格，
    產出每日的總市值、總資產淨值曲線。

    Attributes
    ----------
    engine : PortfolioEngine
        用於回放事件的 PortfolioEngine 實例。
    """

    def __init__(self, engine: PortfolioEngine):
        self.engine = engine

    def generate(
        self,
        events: List[FinancialEvent],
        market_data: Dict[str, pd.DataFrame],
        start_date: date,
        end_date: date,
        initial_cash: float = 0.0,
        *,
        date_col: str = "date",
        price_col: str = "adj_close",
    ) -> pd.DataFrame:
        """
        生成指定時間區間的每日投資組合淨值曲線。

        演算法：
        1. 將事件按日期分組。
        2. 從 start_date 到 end_date 逐日掃描。
        3. 每日先處理當日事件（買賣），更新 FIFO 會計帳。
        4. 使用 LOCF 補值取得各持股當日收盤價。
        5. 計算當日總市值 = Σ(股數 × 收盤價)。
        6. 計算當日總淨值 = 總市值 + 現金餘額。
        7. 記錄每日快照。

        Parameters
        ----------
        events : List[FinancialEvent]
            已排序的 FinancialEvent 序列（按 event_date, sequence_in_day）。
        market_data : Dict[str, pd.DataFrame]
            key 為 stock_id，value 為市場資料 DataFrame。
        start_date : date
            起始日期（含）。
        end_date : date
            結束日期（含）。
        initial_cash : float, default 0.0
            期初現金餘額。
        date_col : str, default "date"
            市場資料的日期欄位名稱。
        price_col : str, default "adj_close"
            市場資料的價格欄位名稱。

        Returns
        -------
        pd.DataFrame
            每日淨值曲線 DataFrame，索引為日期，欄位：
            - cash: 現金餘額
            - market_value: 總市值
            - total_nav: 總資產淨值（市值 + 現金）
            - daily_return_pct: 日報酬率（%）
            - cumulative_return_pct: 累積報酬率（%）
            - {stock_id}: 各股票的個股市值（可選）
        """
        # ── 初始化 ────────────────────────────────────────────────
        self.engine.reset()
        cash_balance = initial_cash

        # 將事件按日期分組
        events_by_date: Dict[date, List[FinancialEvent]] = {}
        for evt in events:
            d = evt.event_date
            if d not in events_by_date:
                events_by_date[d] = []
            events_by_date[d].append(evt)

        # 對每組事件按 sequence_in_day 排序
        for d in events_by_date:
            events_by_date[d].sort(key=lambda e: e.sequence_in_day)

        # 預先對各股票的市場資料做 LOCF 補值
        locf_cache: Dict[str, pd.DataFrame] = {}
        for stock_id, df in market_data.items():
            if df is not None and not df.empty:
                try:
                    locf_cache[stock_id] = apply_locf(
                        df, date_col=date_col, price_col=price_col
                    )
                except (ValueError, TypeError):
                    pass

        # ── 逐日掃描 ──────────────────────────────────────────────
        date_range = pd.date_range(start=start_date, end=end_date, freq="D")
        records = []
        prev_total_nav = 0.0
        initial_nav = 0.0

        for d in date_range:
            current_date = d.date()

            # 1. 處理當日事件
            if current_date in events_by_date:
                for evt in events_by_date[current_date]:
                    self.engine._process_single_event(evt)
                    # 更新現金餘額
                    if isinstance(evt, SecurityTradeEvent):
                        cash_balance += evt.cash_impact
                    elif isinstance(evt, DividendEvent):
                        # 第二階段（發放日）：應收股利銷帳，現金增加
                        if (
                            evt.ex_dividend_date is not None
                            and evt.event_date != evt.ex_dividend_date
                        ):
                            # 尋找對應的已銷帳應收股利
                            for dr in self.engine.dividend_receivables:
                                if (
                                    dr.stock_id == evt.stock_id
                                    and dr.ex_dividend_date == evt.ex_dividend_date
                                    and dr.is_settled
                                ):
                                    cash_balance += dr.net_amount
                                    break

            # 2. 計算當日市值
            total_market_value = 0.0
            stock_values: Dict[str, float] = {}

            for stock_id in self.engine.accountant.get_all_stock_ids():
                lots = self.engine.accountant.get_lots(stock_id)
                total_qty = sum(lot.remaining_quantity for lot in lots)
                if total_qty <= 0:
                    continue

                price = self._get_price_from_cache(
                    stock_id=stock_id,
                    locf_cache=locf_cache,
                    target_date=current_date,
                    price_col=price_col,
                )
                if price is not None:
                    mv = total_qty * price
                    stock_values[stock_id] = round(mv, 2)
                    total_market_value += mv

            total_nav = total_market_value + cash_balance

            # 3. 計算報酬率
            daily_return_pct = 0.0
            cumulative_return_pct = 0.0

            if prev_total_nav > 0:
                daily_return_pct = round(
                    ((total_nav - prev_total_nav) / prev_total_nav) * 100, 4
                )

            if initial_nav == 0 and total_nav > 0:
                initial_nav = total_nav

            if initial_nav > 0:
                cumulative_return_pct = round(
                    ((total_nav - initial_nav) / initial_nav) * 100, 4
                )

            # 4. 記錄快照
            record = {
                "date": current_date,
                "cash": round(cash_balance, 2),
                "market_value": round(total_market_value, 2),
                "total_nav": round(total_nav, 2),
                "daily_return_pct": daily_return_pct,
                "cumulative_return_pct": cumulative_return_pct,
            }
            record.update(stock_values)
            records.append(record)

            prev_total_nav = total_nav

        return pd.DataFrame(records).set_index("date")

    def _get_price_from_cache(
        self,
        stock_id: str,
        locf_cache: Dict[str, pd.DataFrame],
        target_date: date,
        price_col: str,
    ) -> Optional[float]:
        """從 LOCF 快取中取得指定日期的價格。"""
        if stock_id not in locf_cache:
            return None

        filled = locf_cache[stock_id]
        mask = filled["date"] <= target_date
        if not mask.any():
            return None

        return float(filled[mask].iloc[-1][price_col])
