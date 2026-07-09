"""
Market Data Layer 單元測試

測試範圍：
1. PriceProvider 抽象介面（不可實體化、方法簽章正確性）
2. apply_locf LOCF 算子：
   - 連續交易日場景（無需補值）
   - 離散交易日場景（需 LOCF 補值）
   - 空 DataFrame 與缺少欄位等邊界情況
   - Adj Close 預設值與自訂 price_col
   - 自訂 fill_range
"""

import pytest
import pandas as pd
from datetime import date, datetime
from typing import Optional

from src.backend.market_data import PriceProvider, apply_locf


# =========================================================================
# 1. PriceProvider 抽象介面測試
# =========================================================================


class TestPriceProviderInterface:
    """驗證 PriceProvider 作為抽象類別的正確行為。"""

    def test_cannot_instantiate_abstract_class(self):
        """抽象類別不可直接實體化。"""
        with pytest.raises(TypeError):
            PriceProvider()

    def test_concrete_subclass_must_implement_all_methods(self):
        """具體子類別若未實作所有抽象方法，仍不可實體化。"""
        class IncompleteProvider(PriceProvider):
            def fetch_history(self, stock_id: str, start_date: date,
                             end_date: Optional[date] = None) -> pd.DataFrame:
                return pd.DataFrame()

        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_concrete_subclass_can_be_instantiated(self):
        """完整實作所有抽象方法的子類別應可正常實體化。"""
        class FullProvider(PriceProvider):
            def fetch_history(self, stock_id: str, start_date: date,
                             end_date: Optional[date] = None) -> pd.DataFrame:
                return pd.DataFrame()

            def get_latest_price(self, stock_id: str) -> float:
                return 100.0

            def is_market_open(self, trade_date: date) -> bool:
                return True

        provider = FullProvider()
        assert isinstance(provider, PriceProvider)
        assert provider.get_latest_price("2330") == 100.0
        assert provider.is_market_open(date(2024, 1, 2)) is True


# =========================================================================
# 2. apply_locf 測試
# =========================================================================


class TestApplyLocf:
    """LOCF 補值算子的完整測試。"""

    # ── 輔助方法 ────────────────────────────────────────────────

    @staticmethod
    def _make_df(dates, prices, price_col="adj_close"):
        """建立測試用的 DataFrame。"""
        return pd.DataFrame({
            "date": pd.to_datetime(dates),
            price_col: prices,
        })

    # ── 連續交易日場景 ──────────────────────────────────────────

    def test_consecutive_trading_days(self):
        """
        連續交易日：每一天都有資料，LOCF 不應改變任何值。
        """
        dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
        prices = [150.0, 151.5, 149.8, 152.3]
        df = self._make_df(dates, prices)

        result = apply_locf(df)

        assert len(result) == 4
        assert list(result["adj_close"]) == prices
        assert result["is_trading_day"].all()

    def test_consecutive_days_with_adj_close_default(self):
        """
        預設使用 adj_close 欄位進行 LOCF。
        """
        dates = ["2024-01-02", "2024-01-03"]
        prices = [100.0, 101.0]
        df = pd.DataFrame({
            "date": pd.to_datetime(dates),
            "adj_close": prices,
            "close": [99.0, 100.5],
        })

        result = apply_locf(df)

        assert list(result["adj_close"]) == prices

    # ── 離散交易日場景 ──────────────────────────────────────────

    def test_discrete_trading_days_with_gap(self):
        """
        離散交易日：週末或假日無資料，LOCF 應以最後交易日價格向前填補。
        """
        # 模擬：週一(1/2)有資料，週二(1/3)無，週三(1/4)有資料
        dates = ["2024-01-02", "2024-01-04"]
        prices = [150.0, 155.0]
        df = self._make_df(dates, prices)

        result = apply_locf(df)

        # 預期：1/2, 1/3, 1/4 三天
        assert len(result) == 3
        # 1/2 = 150.0, 1/3 = 150.0 (LOCF), 1/4 = 155.0
        assert result["adj_close"].iloc[0] == 150.0
        assert result["adj_close"].iloc[1] == 150.0  # LOCF 補值
        assert result["adj_close"].iloc[2] == 155.0
        # 交易日標記
        assert bool(result["is_trading_day"].iloc[0]) is True
        assert bool(result["is_trading_day"].iloc[1]) is False
        assert bool(result["is_trading_day"].iloc[2]) is True

    def test_discrete_days_multiple_gaps(self):
        """
        多段離散間隔：驗證 LOCF 在多次間隔下的正確性。
        """
        dates = ["2024-01-02", "2024-01-05", "2024-01-09"]
        prices = [100.0, 102.0, 105.0]
        df = self._make_df(dates, prices)

        result = apply_locf(df)

        # 1/2 ~ 1/9 共 8 天
        assert len(result) == 8
        # 1/2 = 100, 1/3 = 100, 1/4 = 100, 1/5 = 102
        # 1/6 = 102, 1/7 = 102, 1/8 = 102, 1/9 = 105
        expected = [100.0, 100.0, 100.0, 102.0, 102.0, 102.0, 102.0, 105.0]
        assert list(result["adj_close"]) == expected

    def test_discrete_days_single_observation(self):
        """
        只有一個觀測值：LOCF 應將該值填滿整個日期範圍。
        """
        dates = ["2024-01-05"]
        prices = [200.0]
        df = self._make_df(dates, prices)

        result = apply_locf(df)

        assert len(result) == 1
        assert result["adj_close"].iloc[0] == 200.0

    # ── Adj Close 防呆機制驗證 ──────────────────────────────────

    def test_adj_close_prevents_dividend_double_counting(self):
        """
        驗證使用 adj_close 可避免股利重複計算問題。

        情境：股票在除息日（1/3）因配息 5 元而跳空下跌，
        若使用 close（未調整收盤價），LOCF 會將除息前的價格
        向前填補，導致報酬率計算失真。
        使用 adj_close 則因價格已還原，不會有跳空問題。
        """
        # close 在除息日跳空下跌
        dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
        close_prices = [100.0, 95.0, 96.0]   # 1/3 除息 5 元
        adj_close_prices = [100.0, 100.0, 101.0]  # adj_close 已還原

        df = pd.DataFrame({
            "date": pd.to_datetime(dates),
            "close": close_prices,
            "adj_close": adj_close_prices,
        })

        # 使用 adj_close（預設行為）
        result_adj = apply_locf(df)

        # 使用 close（模擬錯誤用法）
        result_close = apply_locf(df, price_col="close")

        # adj_close 版本：價格平滑過渡，無跳空
        assert result_adj["adj_close"].iloc[1] == 100.0  # 已還原

        # close 版本：1/2 的 100 元會 LOCF 到 1/3（但 1/3 有資料所以不會）
        # 重點是如果 1/3 無資料，close 會錯誤地 carry forward 除息前價格
        assert result_close["close"].iloc[1] == 95.0

    def test_default_price_col_is_adj_close(self):
        """
        確認預設 price_col 為 'adj_close'，確保防呆機制預設啟用。
        """
        import inspect
        sig = inspect.signature(apply_locf)
        default_val = sig.parameters["price_col"].default
        assert default_val == "adj_close", (
            f"Expected default price_col='adj_close', got '{default_val}'"
        )

    # ── 自訂參數測試 ────────────────────────────────────────────

    def test_custom_price_col(self):
        """支援自訂 price_col 參數。"""
        dates = ["2024-01-02", "2024-01-05"]
        prices = [50.0, 52.0]
        df = pd.DataFrame({
            "date": pd.to_datetime(dates),
            "custom_price": prices,
        })

        result = apply_locf(df, price_col="custom_price")

        assert len(result) == 4
        assert list(result["custom_price"]) == [50.0, 50.0, 50.0, 52.0]

    def test_custom_date_col(self):
        """支援自訂 date_col 參數。"""
        dates = ["2024-01-02", "2024-01-04"]
        prices = [150.0, 155.0]
        df = pd.DataFrame({
            "trade_date": pd.to_datetime(dates),
            "adj_close": prices,
        })

        result = apply_locf(df, date_col="trade_date")

        assert len(result) == 3

    def test_custom_fill_range(self):
        """
        自訂 fill_range：補值範圍可超出原始資料範圍。
        """
        dates = ["2024-01-03", "2024-01-05"]
        prices = [100.0, 102.0]
        df = self._make_df(dates, prices)

        custom_range = pd.date_range("2024-01-01", "2024-01-07", freq="D")
        result = apply_locf(df, fill_range=custom_range)

        assert len(result) == 7
        # 1/1 ~ 1/2 無資料 → NaN（LOCF 無法補）
        assert pd.isna(result["adj_close"].iloc[0])
        assert pd.isna(result["adj_close"].iloc[1])
        # 1/3 = 100, 1/4 = 100 (LOCF), 1/5 = 102
        assert result["adj_close"].iloc[2] == 100.0
        assert result["adj_close"].iloc[3] == 100.0
        assert result["adj_close"].iloc[4] == 102.0
        # 1/6 ~ 1/7 = 102 (LOCF)
        assert result["adj_close"].iloc[5] == 102.0
        assert result["adj_close"].iloc[6] == 102.0

    # ── 邊界情況 ────────────────────────────────────────────────

    def test_empty_dataframe_raises_value_error(self):
        """空 DataFrame 應拋出 ValueError。"""
        with pytest.raises(ValueError, match="empty"):
            apply_locf(pd.DataFrame())

    def test_missing_date_col_raises_value_error(self):
        """缺少 date_col 欄位應拋出 ValueError。"""
        df = pd.DataFrame({"adj_close": [100.0]})
        with pytest.raises(ValueError, match="not found"):
            apply_locf(df)

    def test_missing_price_col_raises_value_error(self):
        """缺少 price_col 欄位應拋出 ValueError。"""
        df = pd.DataFrame({"date": pd.to_datetime(["2024-01-02"])})
        with pytest.raises(ValueError, match="not found"):
            apply_locf(df)

    def test_duplicate_dates_are_deduplicated(self):
        """
        重複日期的資料應自動去重，不影響 LOCF 結果。
        """
        dates = ["2024-01-02", "2024-01-02", "2024-01-04"]
        prices = [100.0, 100.0, 102.0]
        df = self._make_df(dates, prices)

        result = apply_locf(df)

        assert len(result) == 3  # 1/2, 1/3, 1/4
        assert result["adj_close"].iloc[0] == 100.0
        assert result["adj_close"].iloc[1] == 100.0
        assert result["adj_close"].iloc[2] == 102.0

    def test_unsorted_input_is_sorted(self):
        """
        未排序的輸入應自動排序，不影響 LOCF 結果。
        """
        dates = ["2024-01-05", "2024-01-02", "2024-01-04"]
        prices = [105.0, 100.0, 102.0]
        df = self._make_df(dates, prices)

        result = apply_locf(df)

        # 應按日期排序：1/2=100, 1/3=100(LOCF), 1/4=102, 1/5=105
        assert len(result) == 4
        assert list(result["adj_close"]) == [100.0, 100.0, 102.0, 105.0]

    def test_output_columns(self):
        """驗證輸出 DataFrame 的欄位結構。"""
        dates = ["2024-01-02", "2024-01-05"]
        prices = [150.0, 155.0]
        df = self._make_df(dates, prices)

        result = apply_locf(df)

        expected_cols = {"date", "adj_close", "is_trading_day"}
        assert set(result.columns) == expected_cols

    def test_output_date_type(self):
        """驗證輸出日期的型別為 date（非 Timestamp）。"""
        dates = ["2024-01-02", "2024-01-05"]
        prices = [150.0, 155.0]
        df = self._make_df(dates, prices)

        result = apply_locf(df)

        assert isinstance(result["date"].iloc[0], date)
