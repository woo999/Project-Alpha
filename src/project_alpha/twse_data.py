"""Free official Taiwan 50 total-return index data from TWSE."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import json
import time
from typing import Any
from urllib.request import Request, urlopen

import pandas as pd


TWSE_TAIWAN50_ENDPOINT = "https://www.twse.com.tw/rwd/zh/FTSE/TAI50I"


def _parse_roc_date(value: str) -> pd.Timestamp:
    try:
        year, month, day = (int(part) for part in value.split("/"))
        return pd.Timestamp(year=year + 1911, month=month, day=day)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid TWSE ROC date: {value!r}") from exc


def parse_taiwan50_payload(payload: dict[str, Any]) -> pd.DataFrame:
    """Parse one official monthly response without silently dropping rows."""
    if payload.get("stat") != "OK":
        raise ValueError(f"TWSE response status is not OK: {payload.get('stat')!r}")
    expected = ["日期", "臺灣50指數", "臺灣50報酬指數"]
    if payload.get("fields") != expected:
        raise ValueError("TWSE response fields changed")

    records = []
    for row in payload.get("data", []):
        if len(row) != 3:
            raise ValueError("TWSE response row does not contain three fields")
        records.append(
            {
                "timestamp": _parse_roc_date(row[0]),
                "price_index": float(row[1].replace(",", "")),
                "close": float(row[2].replace(",", "")),
            }
        )
    if not records:
        raise ValueError("TWSE response contains no observations")
    frame = pd.DataFrame.from_records(records).set_index("timestamp")
    if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise ValueError("TWSE monthly observations are not chronological and unique")
    return frame


def _month_keys(start: date, end: date) -> list[str]:
    if start > end:
        raise ValueError("start date cannot be after end date")
    keys = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        keys.append(f"{year:04d}{month:02d}01")
        month = month + 1
        if month == 13:
            year, month = year + 1, 1
    return keys


def _fetch_month(month_key: str, *, retries: int) -> pd.DataFrame:
    url = f"{TWSE_TAIWAN50_ENDPOINT}?date={month_key}&response=json"
    for attempt in range(retries + 1):
        try:
            request = Request(
                url,
                headers={"User-Agent": "Project-Alpha research/0.1"},
            )
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
            return parse_taiwan50_payload(payload)
        except Exception:
            if attempt >= retries:
                raise
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError("unreachable")


def fetch_taiwan50_total_return(
    start: date,
    end: date,
    *,
    workers: int = 3,
    retries: int = 2,
) -> pd.DataFrame:
    """Fetch and combine official monthly Taiwan 50 index observations."""
    if workers < 1:
        raise ValueError("workers must be positive")
    if retries < 0:
        raise ValueError("retries cannot be negative")

    frames = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_fetch_month, key, retries=retries): key
            for key in _month_keys(start, end)
        }
        for future in as_completed(futures):
            frames.append(future.result())

    result = pd.concat(frames).sort_index()
    if result.index.has_duplicates:
        raise ValueError("combined TWSE data contains duplicate dates")
    result = result.loc[(result.index.date >= start) & (result.index.date <= end)]
    if result.empty:
        raise ValueError("requested range contains no TWSE observations")
    return result
