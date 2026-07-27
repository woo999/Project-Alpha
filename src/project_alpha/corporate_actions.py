"""Build a total-return series from raw closes and explicit corporate actions."""

from __future__ import annotations

import math

import pandas as pd


ACTION_COLUMNS = ("split_ratio", "cash_dividend")


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

    split_ratio is new shares per old share on the action date.
    cash_dividend is cash paid per pre-action share on that date.
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
