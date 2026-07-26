import numpy as np
import pandas as pd
import pytest

from project_alpha.data_quality import (
    DataQualityError,
    DataQualityPolicy,
    validate_price_series,
)


def make_prices(rows: int = 150) -> pd.Series:
    return pd.Series(
        np.linspace(100.0, 120.0, rows),
        index=pd.date_range("2020-01-01", periods=rows, freq="D"),
    )


def test_valid_data_returns_clean_series_and_report():
    prices = make_prices()
    prices.iloc[10] = np.nan
    policy = DataQualityPolicy(max_missing_fraction=0.01, minimum_rows=100)

    clean, report = validate_price_series(prices, policy)

    assert len(clean) == 149
    assert report.total_rows == 150
    assert report.missing_rows == 1
    assert report.maximum_absolute_return < 0.01


@pytest.mark.parametrize("bad_price", [0.0, -1.0, np.inf, -np.inf])
def test_rejects_nonpositive_and_infinite_prices(bad_price):
    prices = make_prices()
    prices.iloc[20] = bad_price

    with pytest.raises(DataQualityError):
        validate_price_series(prices)


def test_rejects_too_many_missing_rows():
    prices = make_prices()
    prices.iloc[:10] = np.nan

    with pytest.raises(DataQualityError, match="missing fraction"):
        validate_price_series(prices)


def test_rejects_duplicate_or_unsorted_timestamps():
    duplicate = make_prices()
    duplicate.index = list(duplicate.index[:-1]) + [duplicate.index[-2]]
    unsorted = make_prices().sort_index(ascending=False)

    with pytest.raises(DataQualityError, match="duplicate"):
        validate_price_series(duplicate)
    with pytest.raises(DataQualityError, match="sorted"):
        validate_price_series(unsorted)


def test_rejects_extreme_jump_for_manual_investigation():
    prices = make_prices()
    prices.iloc[100] = prices.iloc[99] * 2.0
    policy = DataQualityPolicy(max_absolute_return=0.50, minimum_rows=100)

    with pytest.raises(DataQualityError, match="investigate"):
        validate_price_series(prices, policy)
