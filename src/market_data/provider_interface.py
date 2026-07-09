"""
PriceProvider 抽象介面

定義市場資料提供者（如 Yahoo Finance、TWSE 等）的共同協定。
所有具體 Provider 必須實作此抽象類別。
"""

from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

import pandas as pd


class PriceProvider(ABC):
    """市場收盤價提供者的抽象基底類別。"""

    @abstractmethod
    def fetch_history(
        self,
        stock_id: str,
        start_date: date,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """
        取得指定股票在指定日期區間的歷史收盤價。

        Parameters
        ----------
        stock_id : str
            股票代號（例如 "2330" 代表台積電）。
        start_date : date
            資料起始日（含）。
        end_date : Optional[date]
            資料結束日（含）。若為 None，預設為今天。

        Returns
        -------
        pd.DataFrame
            至少包含以下欄位的 DataFrame：
            - date (datetime64[D]): 交易日
            - close (float64): 收盤價
            - adj_close (float64): 調整後收盤價（已還原股利/分割）
            - volume (int64): 成交量

        Raises
        ------
        ValueError
            若 stock_id 為空字串或格式不合法。
        ConnectionError
            若無法連線至資料來源。
        """
        ...

    @abstractmethod
    def get_latest_price(self, stock_id: str) -> float:
        """
        取得指定股票的最新收盤價。

        Parameters
        ----------
        stock_id : str
            股票代號。

        Returns
        -------
        float
            最新收盤價。

        Raises
        ------
        ValueError
            若 stock_id 為空字串或格式不合法。
        ConnectionError
            若無法連線至資料來源。
        """
        ...

    @abstractmethod
    def is_market_open(self, trade_date: date) -> bool:
        """
        判斷指定日期是否為交易日（非假日、非週末）。

        Parameters
        ----------
        trade_date : date
            欲查詢的日期。

        Returns
        -------
        bool
            True 若該日為交易日，否則 False。
        """
        ...
