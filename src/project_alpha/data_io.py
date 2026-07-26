"""Local market-data loading for reproducible offline research."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_price_csv(
    path: str | Path,
    *,
    timestamp_column: str = "timestamp",
    price_column: str = "close",
) -> pd.Series:
    """Load timestamped close prices without silently fixing unsafe rows."""
    source = Path(path)
    frame = pd.read_csv(source)
    required = {timestamp_column, price_column}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"CSV is missing columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("CSV contains no price rows")

    try:
        timestamps = pd.DatetimeIndex(
            pd.to_datetime(frame[timestamp_column], errors="raise")
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("timestamp column contains invalid dates") from exc

    prices = pd.Series(
        frame[price_column].to_numpy(copy=True),
        index=timestamps,
        name=price_column,
    )
    if not prices.index.is_monotonic_increasing:
        raise ValueError("CSV timestamps must be sorted oldest to newest")
    if prices.index.has_duplicates:
        raise ValueError("CSV contains duplicate timestamps")
    return prices
