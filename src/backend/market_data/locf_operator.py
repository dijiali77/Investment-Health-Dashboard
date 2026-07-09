import pandas as pd
from datetime import date


class MarketDataError(Exception):
    pass


class ERR001_RECOVERABLE(MarketDataError):
    pass


def apply_locf(
    raw_prices: dict[str, list[tuple[date, float]]],
    start_date: date,
    end_date: date,
    is_adj_close: bool = False
) -> dict[date, dict[str, float]]:
    """
    將各 stock_id 的原始日線序列（含交易日空白），
    對齊至 start_date ~ end_date 的完整日曆序列，並以 LOCF 補值。
    """
    if is_adj_close:
        raise ValueError("必須只使用 Close（未調整），絕不可使用 Adj Close 避免股利重複計算")

    if start_date > end_date:
        raise ValueError("start_date cannot be after end_date")

    full_calendar = pd.date_range(start_date, end_date, freq='D')

    result: dict[date, dict[str, float]] = {
        d.date(): {} for d in full_calendar
    }

    for stock_id, price_data in raw_prices.items():
        if not price_data:
            raise ERR001_RECOVERABLE(f"All known prices are missing for {stock_id}")

        dates = [pd.to_datetime(d) for d, _ in price_data]
        prices = [p for _, p in price_data]

        series = pd.Series(data=prices, index=dates)

        # 移除時間部分並確保為 datetime 格式，以便與 full_calendar reindex
        series.index = series.index.normalize()

        # Filter series to only include data up to end_date, so we don't leak future data,
        # and include earlier data so ffill can pick it up for the beginning of the period.
        series = series[series.index <= pd.to_datetime(end_date)]

        if series.empty:
            raise ERR001_RECOVERABLE(f"All known prices are missing for {stock_id} prior to {end_date}")

        # Union the original index with the full calendar so preceding data is included before ffill
        combined_index = series.index.union(full_calendar).sort_values()

        # reindex and ffill over the combined index
        aligned_series = series.reindex(combined_index).ffill()

        # Now keep only the target date range
        aligned_series = aligned_series.reindex(full_calendar)

        # Check if the first day is still NaN
        if pd.isna(aligned_series.iloc[0]):
            raise ERR001_RECOVERABLE(f"Start date {start_date} is NaN and has no preceding price for {stock_id}")

        for dt, price in aligned_series.items():
            result[dt.date()][stock_id] = price

    return result
