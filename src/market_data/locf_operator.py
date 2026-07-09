"""
LOCF (Last Observation Carried Forward) 算子

用於將不連續交易日的收盤價資料補齊為連續日曆日序列。
採用 Adj Close（調整後收盤價）作為補值來源，避免重複扣除股利。
"""

import pandas as pd
from typing import Optional


def apply_locf(
    df: pd.DataFrame,
    *,
    date_col: str = "date",
    price_col: str = "adj_close",
    fill_range: Optional[pd.DatetimeIndex] = None,
) -> pd.DataFrame:
    """
    對不連續的收盤價資料執行 LOCF (Last Observation Carried Forward) 補值。

    將原始交易日資料對齊到完整的日曆日序列，缺失值以最後一個可觀測值向前填補。
    預設使用 adj_close（調整後收盤價）作為補值來源，確保股利已還原，
    避免 Portfolio Engine 在計算報酬率時重複扣除股利。

    Parameters
    ----------
    df : pd.DataFrame
        原始市場資料，必須包含 date_col 與 price_col 兩欄位。
    date_col : str, default "date"
        日期欄位名稱。該欄位應為 datetime64[D] 型別。
    price_col : str, default "adj_close"
        用於 LOCF 補值的價格欄位名稱。
        **強烈建議使用 adj_close（調整後收盤價）**，
        因為 close（未調整收盤價）會在除息日跳空下跌，
        LOCF 會將除息前的價格向前填補，導致報酬率計算失真。
    fill_range : Optional[pd.DatetimeIndex], default None
        自訂的完整日期序列。若為 None，則自動從 df[date_col].min()
        到 df[date_col].max() 生成連續日曆日序列。

    Returns
    -------
    pd.DataFrame
        補值後的 DataFrame，包含完整的日曆日序列，索引為日期。
        欄位：
        - date: 日期
        - {price_col}: LOCF 補值後的價格
        - is_trading_day: bool，標記該日是否為原始交易日

    Raises
    ------
    ValueError
        若 df 為空 DataFrame，或缺少必要欄位。
    TypeError
        若 date_col 欄位無法轉換為 datetime64 型別。

    Examples
    --------
    >>> import pandas as pd
    >>> raw = pd.DataFrame({
    ...     "date": pd.to_datetime(["2024-01-02", "2024-01-05"]),
    ...     "adj_close": [150.0, 155.0],
    ... })
    >>> result = apply_locf(raw)
    >>> len(result)  # 01-02 ~ 01-05 共 4 天
    4
    >>> result.loc["2024-01-04", "adj_close"]
    150.0
    """
    # ── 輸入驗證 ────────────────────────────────────────────────
    if df.empty:
        raise ValueError("Input DataFrame is empty")

    if date_col not in df.columns:
        raise ValueError(f"Column '{date_col}' not found in DataFrame")

    if price_col not in df.columns:
        raise ValueError(f"Column '{price_col}' not found in DataFrame")

    # ── 確保日期欄位為 datetime64 ──────────────────────────────
    df = df.copy()
    try:
        df[date_col] = pd.to_datetime(df[date_col])
    except Exception as exc:
        raise TypeError(
            f"Column '{date_col}' cannot be converted to datetime: {exc}"
        ) from exc

    # ── 排序並去重 ──────────────────────────────────────────────
    df = df.sort_values(date_col).drop_duplicates(subset=[date_col])

    # ── 建立完整日期序列 ────────────────────────────────────────
    if fill_range is not None:
        full_dates = fill_range
    else:
        full_dates = pd.date_range(
            start=df[date_col].min(),
            end=df[date_col].max(),
            freq="D",
        )

    # ── 以日期為索引，對齊到完整序列 ──────────────────────────
    df_indexed = df.set_index(date_col)
    df_indexed = df_indexed.reindex(full_dates)

    # ── LOCF 補值 ───────────────────────────────────────────────
    df_indexed[price_col] = df_indexed[price_col].ffill()

    # ── 標記交易日 ──────────────────────────────────────────────
    df_indexed["is_trading_day"] = df_indexed[price_col].notna()
    # 重新整理：LOCF 後所有有值的日期都應標記交易日（原始交易日）
    # 但我們要保留原始交易日標記，所以用原始資料來標記
    trading_day_mask = df_indexed.index.isin(df[date_col].values)
    df_indexed["is_trading_day"] = trading_day_mask

    # ── 整理輸出 ────────────────────────────────────────────────
    df_indexed.index.name = date_col
    result = df_indexed[[price_col, "is_trading_day"]].reset_index()
    result[date_col] = result[date_col].dt.date

    return result
