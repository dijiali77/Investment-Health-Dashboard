from abc import ABC, abstractmethod
from datetime import date


class PriceProvider(ABC):
    """所有市場資料源的統一介面"""

    @abstractmethod
    def get_price(self, stock_id: str, target_date: date) -> float | None:
        """取得指定日期收盤價（未調整），查無資料回傳 None"""
        ...

    @abstractmethod
    def get_aligned_daily_prices(
        self,
        stock_ids: list[str],
        start_date: date,
        end_date: date,
    ) -> dict[date, dict[str, float]]:
        """
        【v2.1 標準化 LOCF 算子】
        - 傳入一組股票代號與日期區間
        - 必須回傳該區間內『每一天（含週末及國定假日）』的完整股價字典矩陣
        - 內部實作必須採 Last Observation Carried Forward (LOCF) 邏輯（如 pandas.ffill()）
        - 確保 Projection 與 Analytics 取得的時序資料在時間軸上完全對齊，無任何斷點
        - 若所有已知價格均缺失 → ERR001 RECOVERABLE
        """
        ...

    @abstractmethod
    def provider_name(self) -> str:
        """Provider 識別名稱，用於稽核日誌"""
        ...
