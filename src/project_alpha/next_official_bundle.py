"""Discover and prepare the next official paper bundle without a typed date."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from project_alpha.official_close import (
    TPEX_DAILY_CLOSE_URL,
    TWSE_DAILY_CLOSE_URL,
    official_close_for_symbol,
)
from project_alpha.official_paper_bundle import prepare_official_paper_bundle
from project_alpha.official_source import OfficialSourceDownload, fetch_official_source
from project_alpha.paper_tracking import PaperLedger


class OfficialDatesNotSynchronized(ValueError):
    """The two official markets have not published the same latest date."""

    def __init__(self, *, primary_date: str, defensive_date: str) -> None:
        self.primary_date = primary_date
        self.defensive_date = defensive_date
        super().__init__(
            "official close sources are not synchronized: "
            f"0050={primary_date}, 00719B={defensive_date}"
        )


def prepare_next_official_paper_bundle(
    ledger: PaperLedger,
    *,
    primary_action_path: str | Path,
    defensive_action_path: str | Path,
    output_root: str | Path,
    fetcher: Callable[[str], OfficialSourceDownload] = fetch_official_source,
) -> Path | None:
    """Use one pair of official close responses to select the next date."""
    if not ledger.observations:
        raise ValueError("authenticated paper ledger has no initial observation")
    if (
        ledger.spec.primary_symbol != "0050"
        or ledger.spec.defensive_symbol != "00719B"
    ):
        raise ValueError("next-date discovery supports only the 0050/00719B candidate")

    downloads = {
        TWSE_DAILY_CLOSE_URL: fetcher(TWSE_DAILY_CLOSE_URL),
        TPEX_DAILY_CLOSE_URL: fetcher(TPEX_DAILY_CLOSE_URL),
    }
    primary = official_close_for_symbol(
        downloads[TWSE_DAILY_CLOSE_URL].content,
        source_url=downloads[TWSE_DAILY_CLOSE_URL].final_url,
        symbol="0050",
    )
    defensive = official_close_for_symbol(
        downloads[TPEX_DAILY_CLOSE_URL].content,
        source_url=downloads[TPEX_DAILY_CLOSE_URL].final_url,
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

    def cached_fetcher(url: str) -> OfficialSourceDownload:
        return downloads[url] if url in downloads else fetcher(url)

    return prepare_official_paper_bundle(
        observed_on=newest,
        primary_action_path=primary_action_path,
        defensive_action_path=defensive_action_path,
        output_root=output_root,
        fetcher=cached_fetcher,
    )
