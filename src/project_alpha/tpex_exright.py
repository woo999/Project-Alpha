"""Strict reader for official TPEx ex-right/ex-dividend calculation records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import json
import math
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TPEX_EXRIGHT_API = "https://www.tpex.org.tw/www/zh-tw/bulletin/exDailyQ"
REQUIRED_FIELDS = ("除權息日期", "代號", "現金股利")


@dataclass(frozen=True)
class TpexDistributionRecord:
    ex_date: date
    symbol: str
    cash_dividend: float
    raw_row: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["ex_date"] = self.ex_date.isoformat()
        return result


def _parse_roc_date(value: str) -> date:
    parts = value.strip().split("/")
    if len(parts) != 3:
        raise ValueError(f"invalid TPEx ROC date: {value!r}")
    year, month, day = (int(part) for part in parts)
    return date(year + 1911, month, day)


def parse_tpex_exright_payload(
    payload: dict[str, Any],
    *,
    symbol: str,
    expected_date: date,
) -> TpexDistributionRecord:
    """Extract exactly one matching distribution from an official response."""
    if payload.get("stat") != "ok":
        raise ValueError(f"TPEx response status is not ok: {payload.get('stat')!r}")
    tables = payload.get("tables")
    if not isinstance(tables, list) or len(tables) != 1:
        raise ValueError("TPEx response must contain exactly one table")
    table = tables[0]
    fields = table.get("fields")
    rows = table.get("data")
    if not isinstance(fields, list) or not isinstance(rows, list):
        raise ValueError("TPEx response table schema changed")
    missing = [field for field in REQUIRED_FIELDS if field not in fields]
    if missing:
        raise ValueError(f"TPEx response fields changed; missing {missing}")

    date_index = fields.index("除權息日期")
    symbol_index = fields.index("代號")
    dividend_index = fields.index("現金股利")
    matches: list[TpexDistributionRecord] = []
    for row in rows:
        if not isinstance(row, list) or len(row) != len(fields):
            raise ValueError("TPEx response contains a malformed row")
        row_date = _parse_roc_date(str(row[date_index]))
        row_symbol = str(row[symbol_index]).strip()
        if row_symbol != symbol or row_date != expected_date:
            continue
        dividend = float(str(row[dividend_index]).strip())
        if not math.isfinite(dividend) or dividend <= 0:
            raise ValueError("TPEx cash dividend must be finite and positive")
        matches.append(
            TpexDistributionRecord(
                ex_date=row_date,
                symbol=row_symbol,
                cash_dividend=dividend,
                raw_row=tuple(str(value) for value in row),
            )
        )
    if len(matches) != 1:
        raise ValueError(
            f"expected one TPEx record for {symbol} on {expected_date}, "
            f"found {len(matches)}"
        )
    return matches[0]


def fetch_tpex_distribution(
    *,
    symbol: str,
    ex_date: date,
    timeout: float = 30.0,
) -> TpexDistributionRecord:
    """Fetch one dated official calculation record; this never places trades."""
    form = urlencode(
        {
            "startDate": ex_date.strftime("%Y/%m/%d"),
            "endDate": ex_date.strftime("%Y/%m/%d"),
            "response": "json",
        }
    ).encode("ascii")
    request = Request(
        TPEX_EXRIGHT_API,
        data=form,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Project-Alpha research/1.0",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_tpex_exright_payload(
        payload,
        symbol=symbol,
        expected_date=ex_date,
    )
