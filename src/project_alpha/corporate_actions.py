"""Build a total-return series from raw closes and explicit corporate actions."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Iterable

import pandas as pd


ACTION_COLUMNS = ("split_ratio", "cash_dividend")
CSV_COLUMNS = ("date", *ACTION_COLUMNS)


@dataclass(frozen=True)
class CorporateActionCoverage:
    """Result of checking imported actions against an explicit event manifest."""

    action_count: int
    dividend_count: int
    split_count: int
    missing_dividend_dates: tuple[str, ...]
    missing_split_dates: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.missing_dividend_dates and not self.missing_split_dates


def load_corporate_actions_csv(
    path: str | Path,
    *,
    price_index: pd.Index | None = None,
) -> pd.DataFrame:
    """Load explicit corporate actions from a strict, chronological CSV.

    Required columns are ``date``, ``split_ratio`` and ``cash_dividend``.
    Empty cells are rejected rather than interpreted as zero or one, because
    silently filling an event file can materially overstate backtest returns.
    """
    frame = pd.read_csv(path)
    missing = set(CSV_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(
            f"corporate action CSV is missing columns: {sorted(missing)}"
        )
    clean = frame.loc[:, CSV_COLUMNS].copy()
    if clean.empty:
        raise ValueError("corporate action CSV is empty")
    if clean.isna().any().any():
        raise ValueError("corporate action CSV contains empty values")
    try:
        clean["date"] = pd.to_datetime(clean["date"], errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError("corporate action CSV contains an invalid date") from exc
    clean = clean.set_index("date")
    comparison_index = clean.index if price_index is None else price_index
    return validate_corporate_actions(clean, comparison_index)


def audit_expected_actions(
    actions: pd.DataFrame,
    *,
    expected_dividend_dates: Iterable[str | pd.Timestamp] = (),
    expected_split_dates: Iterable[str | pd.Timestamp] = (),
) -> CorporateActionCoverage:
    """Check that every event in an independently sourced manifest is present."""
    clean = validate_corporate_actions(actions, actions.index)

    def normalize(values: Iterable[str | pd.Timestamp], label: str) -> pd.DatetimeIndex:
        try:
            dates = pd.DatetimeIndex(pd.to_datetime(list(values), errors="raise"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} contains an invalid date") from exc
        if dates.has_duplicates:
            raise ValueError(f"{label} contains duplicate dates")
        return dates

    expected_dividends = normalize(
        expected_dividend_dates, "expected_dividend_dates"
    )
    expected_splits = normalize(expected_split_dates, "expected_split_dates")
    actual_dividends = clean.index[clean["cash_dividend"] > 0.0]
    actual_splits = clean.index[clean["split_ratio"] != 1.0]
    missing_dividends = expected_dividends.difference(actual_dividends)
    missing_splits = expected_splits.difference(actual_splits)
    return CorporateActionCoverage(
        action_count=len(clean),
        dividend_count=len(actual_dividends),
        split_count=len(actual_splits),
        missing_dividend_dates=tuple(
            date.strftime("%Y-%m-%d") for date in missing_dividends
        ),
        missing_split_dates=tuple(
            date.strftime("%Y-%m-%d") for date in missing_splits
        ),
    )


def validate_corporate_actions(
    actions: pd.DataFrame,
    price_index: pd.Index,
) -> pd.DataFrame:
    """Validate explicit split and cash-dividend events without guessing."""
    missing = set(ACTION_COLUMNS).difference(actions.columns)
    if missing:
        raise ValueError(
            f"corporate actions are missing columns: {sorted(missing)}"
        )
    clean = actions.loc[:, ACTION_COLUMNS].copy()
    if clean.index.has_duplicates:
        raise ValueError("corporate actions contain duplicate dates")
    if not clean.index.is_monotonic_increasing:
        raise ValueError("corporate actions must be chronological")
    if not clean.index.isin(price_index).all():
        raise ValueError("corporate action date is absent from price series")
    for column in ACTION_COLUMNS:
        clean[column] = pd.to_numeric(clean[column], errors="raise").astype(float)
        if not clean[column].map(math.isfinite).all():
            raise ValueError(f"{column} values must be finite")
    if (clean["split_ratio"] <= 0.0).any():
        raise ValueError("split_ratio must be positive")
    if (clean["cash_dividend"] < 0.0).any():
        raise ValueError("cash_dividend cannot be negative")
    return clean


def build_total_return_index(
    prices: pd.Series,
    actions: pd.DataFrame,
    *,
    initial_value: float = 100.0,
) -> pd.Series:
    """Return a reinvested total-return index normalized to initial_value.

    ``split_ratio`` is new shares per old share on the action date.
    ``cash_dividend`` is cash paid per pre-action share on that date.
    """
    clean_prices = pd.to_numeric(prices, errors="coerce").dropna().astype(float)
    if len(clean_prices) < 2:
        raise ValueError("at least two price observations are required")
    if not clean_prices.index.is_monotonic_increasing:
        raise ValueError("prices must be chronological")
    if clean_prices.index.has_duplicates:
        raise ValueError("prices contain duplicate dates")
    if (clean_prices <= 0.0).any():
        raise ValueError("prices must be positive")
    if not math.isfinite(initial_value) or initial_value <= 0.0:
        raise ValueError("initial_value must be finite and positive")

    clean_actions = validate_corporate_actions(actions, clean_prices.index)
    aligned = pd.DataFrame(
        {
            "split_ratio": 1.0,
            "cash_dividend": 0.0,
        },
        index=clean_prices.index,
    )
    if not clean_actions.empty:
        aligned.loc[clean_actions.index, list(ACTION_COLUMNS)] = clean_actions

    gross_return = (
        aligned["split_ratio"] * clean_prices
        + aligned["cash_dividend"]
    ) / clean_prices.shift(1)
    gross_return.iloc[0] = 1.0
    if (gross_return <= 0.0).any() or not gross_return.map(math.isfinite).all():
        raise ValueError("corporate actions produced invalid total returns")
    result = initial_value * gross_return.cumprod()
    result.name = "total_return_index"
    return result
