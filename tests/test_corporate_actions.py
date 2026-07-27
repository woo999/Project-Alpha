import pandas as pd
import pytest

from project_alpha.corporate_actions import (
    audit_expected_actions,
    build_total_return_index,
    load_corporate_actions_csv,
)


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


def test_load_csv_preserves_explicit_events(tmp_path):
    source = tmp_path / "actions.csv"
    source.write_text(
        "date,split_ratio,cash_dividend\n"
        "2025-01-17,1,2.7\n"
        "2025-06-18,4,0\n"
        "2025-07-21,1,0.36\n",
        encoding="utf-8",
    )
    prices = pd.DatetimeIndex(
        ["2025-01-17", "2025-06-18", "2025-07-21"]
    )

    result = load_corporate_actions_csv(source, price_index=prices)

    assert list(result.columns) == ["split_ratio", "cash_dividend"]
    assert result.loc["2025-06-18", "split_ratio"] == pytest.approx(4.0)
    assert result.loc["2025-07-21", "cash_dividend"] == pytest.approx(0.36)


def test_load_csv_does_not_silently_fill_empty_values(tmp_path):
    source = tmp_path / "actions.csv"
    source.write_text(
        "date,split_ratio,cash_dividend\n2025-01-17,1,\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="empty values"):
        load_corporate_actions_csv(source)


def test_coverage_fails_when_known_event_is_missing():
    dates = pd.DatetimeIndex(["2025-01-17", "2025-06-18"])
    events = actions(dates, [[1.0, 2.7], [4.0, 0.0]])

    result = audit_expected_actions(
        events,
        expected_dividend_dates=["2025-01-17", "2025-07-21"],
        expected_split_dates=["2025-06-18"],
    )

    assert result.complete is False
    assert result.missing_dividend_dates == ("2025-07-21",)
    assert result.missing_split_dates == ()
