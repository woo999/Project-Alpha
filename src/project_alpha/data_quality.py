"""Fail-closed market-data validation for research and paper trading."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd


@dataclass(frozen=True)
class DataQualityPolicy:
    """Limits that must be satisfied before data can enter a backtest."""

    max_missing_fraction: float = 0.01
    max_absolute_return: float = 0.50
    minimum_rows: int = 130

    def validate(self) -> None:
        if not 0.0 <= self.max_missing_fraction < 1.0:
            raise ValueError("max_missing_fraction must be in [0, 1)")
        if self.max_absolute_return <= 0.0:
            raise ValueError("max_absolute_return must be positive")
        if self.minimum_rows < 2:
            raise ValueError("minimum_rows must be at least two")


@dataclass(frozen=True)
class DataQualityReport:
    total_rows: int
    valid_rows: int
    missing_rows: int
    missing_fraction: float
    maximum_absolute_return: float


class DataQualityError(ValueError):
    """Raised when market data is unsafe to use without investigation."""


def validate_price_series(
    prices: pd.Series,
    policy: DataQualityPolicy | None = None,
) -> tuple[pd.Series, DataQualityReport]:
    """Validate and clean a chronological price series.

    Validation is intentionally fail-closed. An extreme return may be a real
    market event or a bad adjustment, so the pipeline stops for investigation
    instead of silently deleting it.
    """
    rules = policy or DataQualityPolicy()
    rules.validate()

    if not isinstance(prices, pd.Series):
        raise TypeError("prices must be a pandas Series")
    if prices.empty:
        raise DataQualityError("price series is empty")
    if not prices.index.is_monotonic_increasing:
        raise DataQualityError("timestamps must be sorted oldest to newest")
    if prices.index.has_duplicates:
        raise DataQualityError("duplicate timestamps detected")

    numeric = pd.to_numeric(prices, errors="coerce").astype(float)
    infinite_count = int(numeric.map(math.isinf).sum())
    if infinite_count:
        raise DataQualityError("infinite prices detected")

    total_rows = len(numeric)
    missing_rows = int(numeric.isna().sum())
    missing_fraction = missing_rows / total_rows
    if missing_fraction > rules.max_missing_fraction:
        raise DataQualityError(
            f"missing fraction {missing_fraction:.2%} exceeds "
            f"{rules.max_missing_fraction:.2%}"
        )

    clean = numeric.dropna()
    if len(clean) < rules.minimum_rows:
        raise DataQualityError(
            f"only {len(clean)} valid rows; need at least {rules.minimum_rows}"
        )
    if (clean <= 0.0).any():
        raise DataQualityError("prices must be strictly positive")

    absolute_returns = clean.pct_change().abs().dropna()
    maximum_absolute_return = (
        float(absolute_returns.max()) if not absolute_returns.empty else 0.0
    )
    if maximum_absolute_return > rules.max_absolute_return:
        raise DataQualityError(
            f"absolute return {maximum_absolute_return:.2%} exceeds "
            f"{rules.max_absolute_return:.2%}; investigate split or bad data"
        )

    report = DataQualityReport(
        total_rows=total_rows,
        valid_rows=len(clean),
        missing_rows=missing_rows,
        missing_fraction=missing_fraction,
        maximum_absolute_return=maximum_absolute_return,
    )
    return clean, report
