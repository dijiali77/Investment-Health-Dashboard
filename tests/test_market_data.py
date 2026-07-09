import pytest
from datetime import date
from src.backend.market_data.locf_operator import apply_locf, ERR001_RECOVERABLE

def test_apply_locf_continuous():
    raw_prices = {
        "2330.TW": [
            (date(2023, 10, 1), 100.0),
            (date(2023, 10, 2), 101.0),
            (date(2023, 10, 3), 102.0),
        ]
    }
    result = apply_locf(raw_prices, date(2023, 10, 1), date(2023, 10, 3))

    assert len(result) == 3
    assert result[date(2023, 10, 1)]["2330.TW"] == 100.0
    assert result[date(2023, 10, 2)]["2330.TW"] == 101.0
    assert result[date(2023, 10, 3)]["2330.TW"] == 102.0


def test_apply_locf_discontinuous_with_holiday():
    # 假設 10/2, 10/3 是週末/連假無交易
    raw_prices = {
        "2330.TW": [
            (date(2023, 10, 1), 100.0),
            (date(2023, 10, 4), 105.0),
        ]
    }
    result = apply_locf(raw_prices, date(2023, 10, 1), date(2023, 10, 4))

    assert len(result) == 4
    assert result[date(2023, 10, 1)]["2330.TW"] == 100.0
    assert result[date(2023, 10, 2)]["2330.TW"] == 100.0 # LOCF filled
    assert result[date(2023, 10, 3)]["2330.TW"] == 100.0 # LOCF filled
    assert result[date(2023, 10, 4)]["2330.TW"] == 105.0


def test_apply_locf_preceding_price_forward_fill():
    # 測試給定區間前的資料，是否能補到區間開頭
    raw_prices = {
        "2330.TW": [
            (date(2023, 9, 29), 95.0),
            (date(2023, 10, 4), 105.0),
        ]
    }
    result = apply_locf(raw_prices, date(2023, 10, 1), date(2023, 10, 4))

    assert result[date(2023, 10, 1)]["2330.TW"] == 95.0
    assert result[date(2023, 10, 2)]["2330.TW"] == 95.0
    assert result[date(2023, 10, 3)]["2330.TW"] == 95.0
    assert result[date(2023, 10, 4)]["2330.TW"] == 105.0


def test_apply_locf_missing_first_day():
    # 如果第一天無法補值，應拋出 ERR001_RECOVERABLE
    raw_prices = {
        "2330.TW": [
            (date(2023, 10, 4), 105.0),
        ]
    }
    with pytest.raises(ERR001_RECOVERABLE, match="Start date .* is NaN"):
        apply_locf(raw_prices, date(2023, 10, 1), date(2023, 10, 4))


def test_apply_locf_prevent_adj_close():
    raw_prices = {
        "2330.TW": [
            (date(2023, 10, 1), 100.0),
        ]
    }
    with pytest.raises(ValueError, match="必須只使用 Close（未調整），絕不可使用 Adj Close"):
        apply_locf(raw_prices, date(2023, 10, 1), date(2023, 10, 4), is_adj_close=True)
