import pandas as pd
import pytest

from project_alpha.corporate_actions import build_total_return_index


def actions(index, rows):
    return pd.DataFrame(
        rows,
        index=pd.DatetimeIndex(index),
        columns=["split_ratio", "cash_dividend"],
    )


def test_split_does_not_create_a_false_loss():
    dates = pd.date_range("2025-01-01", periods=3, freq="D")
    prices = pd.Series([100.0, 25.0, 26.0], index=dates)
    events = actions([dates[1]], [[4.0, 0.0]])

    result = build_total_return_index(prices, events)

    assert result.iloc[0] == pytest.approx(100.0)
    assert result.iloc[1] == pytest.approx(100.0)
    assert result.iloc[2] == pytest.approx(104.0)


def test_cash_dividend_is_reinvested_in_total_return():
    dates = pd.date_range("2025-01-01", periods=3, freq="D")
    prices = pd.Series([100.0, 98.0, 99.0], index=dates)
    events = actions([dates[1]], [[1.0, 2.0]])

    result = build_total_return_index(prices, events)

    assert result.iloc[1] == pytest.approx(100.0)
    assert result.iloc[2] == pytest.approx(100.0 * 99.0 / 98.0)


def test_combined_split_and_dividend_use_pre_action_share_basis():
    dates = pd.date_range("2025-01-01", periods=2, freq="D")
    prices = pd.Series([100.0, 24.5], index=dates)
    events = actions([dates[1]], [[4.0, 2.0]])

    result = build_total_return_index(prices, events)

    assert result.iloc[1] == pytest.approx(100.0)


def test_action_date_must_exist_in_prices():
    dates = pd.date_range("2025-01-01", periods=2, freq="D")
    prices = pd.Series([100.0, 101.0], index=dates)
    events = actions([pd.Timestamp("2025-01-03")], [[1.0, 2.0]])

    with pytest.raises(ValueError, match="absent"):
        build_total_return_index(prices, events)
