"""Strict parser for Mitake desktop daily-history text exports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
from pathlib import Path


@dataclass(frozen=True)
class MitakeDailyBar:
    observed_on: date
    open: float
    high: float
    low: float
    close: float
    volume: int


def load_mitake_daily_export(
    path: str | Path,
    *,
    expected_symbol: str,
) -> tuple[MitakeDailyBar, ...]:
    """Read a complete Mitake export without repairing unsafe input silently."""
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    if not lines or f"商品代碼:{expected_symbol}" not in lines[0]:
        raise ValueError(f"Mitake export is not for expected symbol {expected_symbol}")

    bars: list[MitakeDailyBar] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.startswith("'"):
            continue
        fields = line.split("\t")
        if len(fields) != 6:
            raise ValueError(f"invalid Mitake row at line {line_number}")
        try:
            observed_on = datetime.strptime(
                fields[0][1:], "%Y/%m/%d %H:%M"
            ).date()
            open_price, high, low, close = (float(value) for value in fields[1:5])
            volume = int(fields[5])
        except ValueError as exc:
            raise ValueError(
                f"invalid Mitake value at line {line_number}"
            ) from exc
        prices = (open_price, high, low, close)
        if any(not math.isfinite(value) or value <= 0 for value in prices):
            raise ValueError(f"non-positive or non-finite price at line {line_number}")
        # The export can contain legacy opening-auction values outside the
        # reported intraday high/low.  Close is the paper-accounting input, so
        # require only a coherent high/low range containing the close.
        if high < max(low, close) or low > min(high, close):
            raise ValueError(f"inconsistent OHLC values at line {line_number}")
        if volume < 0:
            raise ValueError(f"negative volume at line {line_number}")
        bars.append(
            MitakeDailyBar(
                observed_on=observed_on,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )

    if not bars:
        raise ValueError("Mitake export contains no daily rows")
    dates = [bar.observed_on for bar in bars]
    if dates != sorted(dates):
        raise ValueError("Mitake daily rows must be sorted oldest to newest")
    if len(dates) != len(set(dates)):
        raise ValueError("Mitake export contains duplicate dates")
    return tuple(bars)


def latest_common_bar(
    primary: tuple[MitakeDailyBar, ...],
    defensive: tuple[MitakeDailyBar, ...],
    *,
    after: date,
) -> tuple[MitakeDailyBar, MitakeDailyBar]:
    """Return the latest common date after a frozen cutoff."""
    primary_by_date = {bar.observed_on: bar for bar in primary}
    defensive_by_date = {bar.observed_on: bar for bar in defensive}
    common = sorted(
        date_value
        for date_value in primary_by_date.keys() & defensive_by_date.keys()
        if date_value > after
    )
    if not common:
        raise ValueError("Mitake exports contain no common date after cutoff")
    latest = common[-1]
    return primary_by_date[latest], defensive_by_date[latest]
