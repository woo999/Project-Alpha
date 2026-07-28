"""Batch daily paper-ledger updates from validated market bars and actions."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
import math
from pathlib import Path

from project_alpha.mitake import MitakeDailyBar
from project_alpha.paper_tracking import PaperLedger
from project_alpha.paper_update import append_mark_to_market


@dataclass(frozen=True)
class PaperAction:
    split_ratio: float
    cash_dividend: float


@dataclass(frozen=True)
class DailyUpdateResult:
    appended_dates: tuple[date, ...]
    stopped_before_rebalance: bool


def load_paper_actions(path: str | Path) -> dict[date, PaperAction]:
    """Load a strict action file without silently filling malformed events."""
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != (
            "date",
            "split_ratio",
            "cash_dividend",
        ):
            raise ValueError("corporate action CSV columns do not match schema")
        actions: dict[date, PaperAction] = {}
        previous_date: date | None = None
        for row_number, row in enumerate(reader, start=2):
            try:
                event_date = date.fromisoformat(row["date"])
                split_ratio = float(row["split_ratio"])
                cash_dividend = float(row["cash_dividend"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"invalid corporate action at row {row_number}"
                ) from exc
            if previous_date is not None and event_date <= previous_date:
                raise ValueError(
                    "corporate action dates must be unique and chronological"
                )
            if not math.isfinite(split_ratio) or split_ratio <= 0:
                raise ValueError("split_ratio must be finite and positive")
            if not math.isfinite(cash_dividend) or cash_dividend < 0:
                raise ValueError("cash_dividend must be finite and non-negative")
            actions[event_date] = PaperAction(split_ratio, cash_dividend)
            previous_date = event_date
    if not actions:
        raise ValueError("corporate action CSV is empty")
    return actions


def append_common_daily_bars(
    ledger: PaperLedger,
    pairs: tuple[tuple[MitakeDailyBar, MitakeDailyBar], ...],
    *,
    primary_actions: dict[date, PaperAction],
    defensive_actions: dict[date, PaperAction],
) -> DailyUpdateResult:
    """Append consecutive non-rebalance observations and stop before trading.

    Splits are deliberately rejected because they require an explicit unit
    conversion before valuation.  The function never places or suggests an
    order.
    """
    appended: list[date] = []
    stopped_before_rebalance = False
    for primary_bar, defensive_bar in pairs:
        if primary_bar.observed_on != defensive_bar.observed_on:
            raise ValueError("daily bar pair dates do not match")
        event_date = primary_bar.observed_on
        if ledger.spec.is_rebalance_observation(len(ledger.observations) + 1):
            stopped_before_rebalance = True
            break
        primary_action = primary_actions.get(event_date, PaperAction(1.0, 0.0))
        defensive_action = defensive_actions.get(
            event_date, PaperAction(1.0, 0.0)
        )
        if (
            not math.isclose(primary_action.split_ratio, 1.0)
            or not math.isclose(defensive_action.split_ratio, 1.0)
        ):
            raise ValueError(
                f"split on {event_date.isoformat()} requires explicit unit adjustment"
            )
        append_mark_to_market(
            ledger,
            observed_on=event_date,
            primary_close=primary_bar.close,
            defensive_close=defensive_bar.close,
            primary_cash_dividend=primary_action.cash_dividend,
            defensive_cash_dividend=defensive_action.cash_dividend,
        )
        appended.append(event_date)
    return DailyUpdateResult(tuple(appended), stopped_before_rebalance)
