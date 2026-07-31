"""Discover and prepare the next official paper bundle without a typed date."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from project_alpha.official_close import (
    TPEX_DAILY_CLOSE_URL,
    TWSE_DAILY_CLOSE_URL,
    official_close_for_symbol,
)
from project_alpha.official_paper_bundle import prepare_official_paper_bundle
from project_alpha.official_source import OfficialSourceDownload, fetch_official_source
from project_alpha.paper_tracking import PaperLedger


TAIPEI_TIME_ZONE = ZoneInfo("Asia/Taipei")
SAME_DAY_OFFICIAL_NOT_BEFORE = time(14, 30)


class OfficialDatesNotSynchronized(ValueError):
    """The two official markets have not published the same latest date."""

    def __init__(self, *, primary_date: str, defensive_date: str) -> None:
        self.primary_date = primary_date
        self.defensive_date = defensive_date
        super().__init__(
            "official close sources are not synchronized: "
            f"0050={primary_date}, 00719B={defensive_date}"
        )


class OfficialDateNotMature(ValueError):
    """The source date is today but the conservative close cutoff has not passed."""

    def __init__(self, *, observed_on: date) -> None:
        self.observed_on = observed_on.isoformat()
        self.available_after = (
            f"{self.observed_on}T{SAME_DAY_OFFICIAL_NOT_BEFORE.isoformat()}"
            "+08:00"
        )
        super().__init__(
            "same-day official close is not mature before "
            f"{self.available_after}"
        )


class OfficialSourceContentInvalid(ValueError):
    """An official response arrived but could not be safely interpreted."""

    def __init__(self, *, source_url: str, detail: str) -> None:
        self.source_url = source_url
        self.detail = detail
        super().__init__(f"invalid official source content from {source_url}: {detail}")


def _official_close_from_download(
    download: OfficialSourceDownload,
    *,
    symbol: str,
):
    try:
        return official_close_for_symbol(
            download.content,
            source_url=download.final_url,
            symbol=symbol,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise OfficialSourceContentInvalid(
            source_url=download.final_url,
            detail=type(exc).__name__,
        ) from exc


def prepare_next_official_paper_bundle(
    ledger: PaperLedger,
    *,
    primary_action_path: str | Path,
    defensive_action_path: str | Path,
    output_root: str | Path,
    fetcher: Callable[[str], OfficialSourceDownload] = fetch_official_source,
    now: datetime | None = None,
) -> Path | None:
    """Use one pair of official close responses to select the next date."""
    if not ledger.observations:
        raise ValueError("authenticated paper ledger has no initial observation")
    if (
        ledger.spec.primary_symbol != "0050"
        or ledger.spec.defensive_symbol != "00719B"
    ):
        raise ValueError("next-date discovery supports only the 0050/00719B candidate")

    close_urls = (TWSE_DAILY_CLOSE_URL, TPEX_DAILY_CLOSE_URL)
    with ThreadPoolExecutor(max_workers=len(close_urls)) as executor:
        downloads = dict(zip(close_urls, executor.map(fetcher, close_urls), strict=True))
    primary = _official_close_from_download(
        downloads[TWSE_DAILY_CLOSE_URL],
        symbol="0050",
    )
    defensive = _official_close_from_download(
        downloads[TPEX_DAILY_CLOSE_URL],
        symbol="00719B",
    )
    if primary.observed_on != defensive.observed_on:
        raise OfficialDatesNotSynchronized(
            primary_date=primary.observed_on.isoformat(),
            defensive_date=defensive.observed_on.isoformat(),
        )
    newest = primary.observed_on
    last_observed_on = ledger.observations[-1].observed_on
    if newest < last_observed_on:
        raise ValueError("official close date is older than the paper ledger")
    if newest == last_observed_on:
        return None
    checked_at = now or datetime.now(TAIPEI_TIME_ZONE)
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise ValueError("official maturity clock must be timezone-aware")
    taipei_now = checked_at.astimezone(TAIPEI_TIME_ZONE)
    if newest > taipei_now.date():
        raise ValueError("official close date is in the future")
    if (
        newest == taipei_now.date()
        and taipei_now.time().replace(tzinfo=None)
        < SAME_DAY_OFFICIAL_NOT_BEFORE
    ):
        raise OfficialDateNotMature(observed_on=newest)

    def cached_fetcher(url: str) -> OfficialSourceDownload:
        return downloads[url] if url in downloads else fetcher(url)

    return prepare_official_paper_bundle(
        observed_on=newest,
        primary_action_path=primary_action_path,
        defensive_action_path=defensive_action_path,
        output_root=output_root,
        fetcher=cached_fetcher,
    )
