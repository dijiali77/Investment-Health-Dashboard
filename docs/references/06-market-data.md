# 第二層｜Market Data Layer

> **依賴章節**：`00-overview.md`、`04-domain-models.md`（5.2 Market Data 模型）

---

## 第七章　第二層｜Market Data Layer（LOCF 算子，解決 E5）

### 7.1 PriceProvider 抽象介面（v2.1 升級）

> **E5 問題**：週末與休市期間市價缺失，導致時序指標計算中斷或出現 NaN。
>
> **v2.1 解法**：所有 Provider 必須實作 `get_aligned_daily_prices`，強制輸出含 LOCF 補值的完整連續向量。

```python
# src/market_data/provider_interface.py
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
```

**Provider 優先序**（可於 `config/settings.py` 設定）：

```
1. YahooFinanceProvider（預設，免費，有快取）
2. TWSEOpenDataProvider（台灣證交所開放資料，官方）
3. AlphaVantageProvider（需 API Key，有 SLA）
4. LocalCsvProvider      （離線測試用）
```

若 Provider 1 回傳 `ERR008 ProviderUnavailable`，自動切換至 Provider 2，並記錄 `confidence = "Medium"`。

### 7.2 LOCF 算子實作規格

```python
# src/market_data/locf_operator.py
import pandas as pd
from datetime import date

def apply_locf(
    raw_prices: dict[str, list[tuple[date, float]]],
    start_date: date,
    end_date: date,
) -> dict[date, dict[str, float]]:
    """
    將各 stock_id 的原始日線序列（含交易日空白），
    對齊至 start_date ~ end_date 的完整日曆序列，並以 LOCF 補值。

    實作步驟：
    1. 建立完整日曆序列：pd.date_range(start_date, end_date, freq='D')
    2. 對每個 stock_id 建立 pd.Series，index = 交易日，value = 收盤價
    3. 以 .reindex(full_calendar).ffill() 補值
    4. 對齊後的第一天若仍為 NaN（無前置已知價）→ ERR001 RECOVERABLE
    5. 轉換為 dict[date, dict[str, float]] 格式回傳
    """
    ...
```

### 7.3 台股代碼解析規則

```python
def resolve_ticker(stock_id: str, provider: PriceProvider) -> str:
    # 1. 查 ticker_overrides.yaml
    # 2. 嘗試 {stock_id}.TW
    # 3. Fallback {stock_id}.TWO
    # 4. 兩者皆失敗 → ERR002 RECOVERABLE
```

### 7.4 ⚠️ 股利重複計算陷阱（重要，必須遵守）

**必須只使用 `Close`（未調整），絕不可使用 `Adj Close`**。

理由：`Adj Close` 在除息日會向下調整歷史收盤價，若同時從 `bank_ledger.csv` 已記錄了股利入帳，將導致股利被計算兩次（一次在 NAV 下跌中隱含，一次在 `DividendEvent` 現金入帳）。

快取路徑：`data/cache/prices/{provider_name}/{stock_id}.parquet`，不同 Provider 的快取分開存放。

---
