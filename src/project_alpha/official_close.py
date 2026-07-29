"""Strict reconciliation of Mitake closes with free official daily data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import math
from urllib.parse import urlparse


TWSE_DAILY_CLOSE_URL = (
    "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_AVG_ALL"
)
TPEX_DAILY_CLOSE_URL = (
    "https://www.tpex.org.tw/openapi/v1/"
    "tpex_mainboard_daily_close_quotes"
)


@dataclass(frozen=True)
class OfficialClose:
    observed_on: date
    symbol: str
    close: float


def _roc_date(value: object) -> date:
    text = str(value).strip().replace("/", "")
    if len(text) != 7 or not text.isdigit():
        raise ValueError(f"invalid official close date: {value!r}")
    return date(int(text[:3]) + 1911, int(text[3:5]), int(text[5:7]))


def _price(value: object) -> float:
    try:
        result = float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError) as exc:
        raise ValueError("official close is not numeric") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError("official close must be finite and positive")
    return result


def parse_twse_daily_closes(payload: bytes) -> tuple[OfficialClose, ...]:
    rows = json.loads(payload.decode("utf-8"))
    if not isinstance(rows, list):
        raise ValueError("TWSE daily closes must be a JSON array")
    required = {"Date", "Code", "ClosingPrice"}
    result = []
    for row in rows:
        if not isinstance(row, dict) or not required.issubset(row):
            raise ValueError("TWSE daily close schema changed")
        result.append(
            OfficialClose(
                observed_on=_roc_date(row["Date"]),
                symbol=str(row["Code"]).strip(),
                close=_price(row["ClosingPrice"]),
            )
        )
    return tuple(result)


def parse_tpex_daily_closes(payload: bytes) -> tuple[OfficialClose, ...]:
    rows = json.loads(payload.decode("utf-8"))
    if not isinstance(rows, list):
        raise ValueError("TPEx daily closes must be a JSON array")
    required = {"資料日期", "代號", "收盤"}
    result = []
    for row in rows:
        if not isinstance(row, dict) or not required.issubset(row):
            raise ValueError("TPEx daily close schema changed")
        result.append(
            OfficialClose(
                observed_on=_roc_date(row["資料日期"]),
                symbol=str(row["代號"]).strip(),
                close=_price(row["收盤"]),
            )
        )
    return tuple(result)


def verify_official_close(
    payload: bytes,
    *,
    source_url: str,
    symbol: str,
    expected_date: date,
    expected_close: float,
) -> None:
    """Require exactly one official symbol/date row equal to the Mitake close."""
    parsed = urlparse(source_url)
    host = (parsed.hostname or "").lower()
    if (
        host == "openapi.twse.com.tw"
        and parsed.path.endswith("/STOCK_DAY_AVG_ALL")
    ):
        rows = parse_twse_daily_closes(payload)
    elif (
        host == "www.tpex.org.tw"
        and parsed.path.endswith("/tpex_mainboard_daily_close_quotes")
    ):
        rows = parse_tpex_daily_closes(payload)
    else:
        raise ValueError("unsupported official daily close source")
    matches = [
        row
        for row in rows
        if row.symbol == symbol and row.observed_on == expected_date
    ]
    if len(matches) != 1:
        raise ValueError("official close must contain exactly one symbol/date row")
    if not math.isclose(
        matches[0].close,
        expected_close,
        rel_tol=0,
        abs_tol=1e-9,
    ):
        raise ValueError("Mitake close conflicts with official daily close")
