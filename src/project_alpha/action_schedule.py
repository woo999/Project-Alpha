"""Strict daily checks against official TWSE and TPEx action schedules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import math
from pathlib import Path
from urllib.parse import urlparse

from project_alpha.paper_daily import PaperAction


@dataclass(frozen=True)
class ScheduledAction:
    event_date: date
    symbol: str
    split_ratio: float
    cash_dividend: float | None


def _roc_compact_date(value: object) -> date:
    text = str(value).strip().replace("/", "")
    if len(text) != 7 or not text.isdigit():
        raise ValueError(f"invalid ROC action date: {value!r}")
    return date(int(text[:3]) + 1911, int(text[3:5]), int(text[5:7]))


def _number(value: object, *, default: float = 0.0) -> float:
    text = str(value).strip().replace(",", "")
    result = default if text == "" else float(text)
    if not math.isfinite(result) or result < 0:
        raise ValueError("official action amount must be finite and non-negative")
    return result


def _announced_cash_dividend(value: object) -> float | None:
    text = str(value).strip()
    if text in {"", "尚未公告"}:
        return None
    return _number(text)


def parse_twse_action_schedule(payload: bytes) -> tuple[ScheduledAction, ...]:
    rows = json.loads(payload.decode("utf-8"))
    if not isinstance(rows, list):
        raise ValueError("TWSE action schedule must be a JSON array")
    required = {"Date", "Code", "StockDividendRatio", "CashDividend"}
    result = []
    for row in rows:
        if not isinstance(row, dict) or not required.issubset(row):
            raise ValueError("TWSE action schedule schema changed")
        stock_ratio = _number(row["StockDividendRatio"])
        result.append(
            ScheduledAction(
                _roc_compact_date(row["Date"]),
                str(row["Code"]).strip(),
                1.0 + stock_ratio,
                _announced_cash_dividend(row["CashDividend"]),
            )
        )
    return tuple(result)


def parse_tpex_action_schedule(payload: bytes) -> tuple[ScheduledAction, ...]:
    rows = json.loads(payload.decode("utf-8"))
    if not isinstance(rows, list):
        raise ValueError("TPEx action schedule must be a JSON array")
    required = {
        "ExRrightsExDividendDate",
        "SecuritiesCompanyCode",
        "StockDividendRatio",
        "CashDividend",
    }
    result = []
    for row in rows:
        if not isinstance(row, dict) or not required.issubset(row):
            raise ValueError("TPEx action schedule schema changed")
        stock_ratio = _number(row["StockDividendRatio"])
        result.append(
            ScheduledAction(
                _roc_compact_date(row["ExRrightsExDividendDate"]),
                str(row["SecuritiesCompanyCode"]).strip(),
                1.0 + stock_ratio,
                _announced_cash_dividend(row["CashDividend"]),
            )
        )
    return tuple(result)


def verify_official_action_day(
    source_path: str | Path,
    *,
    source_url: str,
    symbol: str,
    event_date: date,
    actions: dict[date, PaperAction],
) -> None:
    """Require the saved official schedule and action CSV to agree for one day."""
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    payload = Path(source_path).read_bytes()
    if (
        hostname == "openapi.twse.com.tw"
        and parsed.path.endswith("/exchangeReport/TWT48U_ALL")
    ):
        schedule = parse_twse_action_schedule(payload)
    elif (
        hostname == "www.tpex.org.tw"
        and parsed.path.endswith("/tpex_exright_prepost")
    ):
        schedule = parse_tpex_action_schedule(payload)
    else:
        raise ValueError("unsupported official action schedule source")
    matches = [
        item
        for item in schedule
        if item.symbol == symbol and item.event_date == event_date
    ]
    if len(matches) > 1:
        raise ValueError("official action schedule contains duplicate symbol/date")
    expected = actions.get(event_date)
    if not matches and expected is None:
        return
    if not matches or expected is None:
        raise ValueError("official action schedule and action CSV disagree")
    item = matches[0]
    if item.cash_dividend is None:
        raise ValueError("official cash dividend is not yet announced")
    if not math.isclose(item.split_ratio, expected.split_ratio, abs_tol=1e-12):
        raise ValueError("official split ratio conflicts with action CSV")
    if not math.isclose(
        item.cash_dividend, expected.cash_dividend, abs_tol=1e-12
    ):
        raise ValueError("official cash dividend conflicts with action CSV")
