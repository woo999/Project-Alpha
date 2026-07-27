"""Free official ETF dividend records from the Taiwan Stock Exchange."""

from __future__ import annotations

from datetime import date
from html.parser import HTMLParser
import math
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


TWSE_DIVIDEND_URL = (
    "https://www.twse.com.tw/en/ETFortune-institute/dividendList"
)
EXPECTED_HEADER = (
    "ETF Code",
    "ETF Name",
    "Ex-dividend Date",
    "Dividend Payment Date",
    "Cash Dividend (NT$/Per beneficiary unit)",
    "Year Announced",
)


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"th", "td"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


def parse_twse_dividend_html(html: str, *, etf_code: str) -> pd.DataFrame:
    """Parse a TWSE dividend table and reject schema drift or malformed rows."""
    parser = _TableParser()
    parser.feed(html)
    table = next(
        (rows for rows in parser.tables if rows and tuple(rows[0]) == EXPECTED_HEADER),
        None,
    )
    if table is None:
        raise ValueError("TWSE dividend table schema changed or is absent")

    records = []
    for row in table[1:]:
        if len(row) != len(EXPECTED_HEADER):
            raise ValueError("TWSE dividend row has an unexpected field count")
        if row[0] != etf_code:
            continue
        try:
            ex_date = pd.to_datetime(row[2], format="%Y/%m/%d", errors="raise")
            payment_date = pd.to_datetime(
                row[3], format="%Y/%m/%d", errors="raise"
            )
            cash_dividend = float(row[4].replace(",", ""))
            announced_year = int(row[5])
        except (TypeError, ValueError) as exc:
            raise ValueError("TWSE dividend row contains an invalid value") from exc
        if not math.isfinite(cash_dividend) or cash_dividend <= 0.0:
            raise ValueError("TWSE cash dividend must be finite and positive")
        records.append(
            {
                "date": ex_date,
                "payment_date": payment_date,
                "cash_dividend": cash_dividend,
                "announced_year": announced_year,
            }
        )
    if not records:
        raise ValueError(f"TWSE response contains no dividends for {etf_code}")
    result = pd.DataFrame.from_records(records).set_index("date").sort_index()
    if result.index.has_duplicates:
        raise ValueError("TWSE dividend records contain duplicate ex-dividend dates")
    return result


def fetch_twse_etf_dividends(
    etf_code: str,
    start_year: int,
    end_year: int,
    *,
    pause_seconds: float = 1.0,
    retries: int = 2,
) -> pd.DataFrame:
    """Fetch official dividends one year at a time with conservative pacing."""
    current_year = date.today().year
    if (
        not etf_code
        or not etf_code.isascii()
        or not etf_code.isalnum()
        or etf_code != etf_code.upper()
    ):
        raise ValueError("etf_code must contain uppercase ASCII letters or digits")
    if start_year > end_year:
        raise ValueError("start_year cannot be after end_year")
    if start_year < 2003 or end_year > current_year:
        raise ValueError(f"years must be between 2003 and {current_year}")
    if pause_seconds < 0.0:
        raise ValueError("pause_seconds cannot be negative")
    if retries < 0:
        raise ValueError("retries cannot be negative")

    frames = []
    for year in range(start_year, end_year + 1):
        query = urlencode(
            {"startDate": year, "endDate": year, "stkNo": etf_code}
        )
        url = f"{TWSE_DIVIDEND_URL}?{query}"
        for attempt in range(retries + 1):
            try:
                request = Request(
                    url,
                    headers={"User-Agent": "Project-Alpha research/0.1"},
                )
                with urlopen(request, timeout=30) as response:
                    html = response.read().decode("utf-8")
                break
            except Exception:
                if attempt >= retries:
                    raise
                time.sleep(1.0 * (attempt + 1))
        try:
            frames.append(parse_twse_dividend_html(html, etf_code=etf_code))
        except ValueError as exc:
            if "contains no dividends" not in str(exc):
                raise
        if pause_seconds:
            time.sleep(pause_seconds)
    if not frames:
        raise ValueError("requested range contains no ETF dividends")
    result = pd.concat(frames).sort_index()
    if result.index.has_duplicates:
        raise ValueError("combined TWSE dividends contain duplicate dates")
    return result
