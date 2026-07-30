from datetime import date
import json

import pytest

from project_alpha.daily_action_evidence import (
    TPEX_ACTION_SCHEDULE_URL,
    TWSE_ACTION_SCHEDULE_URL,
)
from project_alpha.next_official_bundle import prepare_next_official_paper_bundle
from project_alpha.official_close import TPEX_DAILY_CLOSE_URL, TWSE_DAILY_CLOSE_URL
from project_alpha.official_paper_bundle import load_official_paper_bundle
from project_alpha.official_source import OfficialSourceDownload
from project_alpha.paper_tracking import CandidateSpec, PaperLedger, PaperObservation


def _ledger(last=date(2026, 7, 29)):
    ledger = PaperLedger(
        CandidateSpec(
            candidate_id="candidate",
            declared_on=date(2026, 7, 28),
            historical_cutoff=date(2026, 7, 27),
            primary_symbol="0050",
            defensive_symbol="00719B",
            primary_weight=0.6,
            defensive_weight=0.4,
            rebalance_interval_trading_days=63,
        )
    )
    ledger.append(
        PaperObservation(
            observed_on=last,
            portfolio_value=100,
            primary_close=1,
            defensive_close=1,
            primary_units=60,
            defensive_units=40,
            cash_balance=0,
        )
    )
    return ledger


def _actions(path):
    path.write_text("date,split_ratio,cash_dividend\n2026-07-21,1,0\n", encoding="utf-8")


def _download(rows, url):
    return OfficialSourceDownload(json.dumps(rows).encode(), url, "application/json")


def _fetcher(twse_date="1150730", tpex_date="1150730"):
    def fetch(url):
        if url == TWSE_DAILY_CLOSE_URL:
            rows = [{"Date": twse_date, "Code": "0050", "ClosingPrice": "94.00"}]
        elif url == TPEX_DAILY_CLOSE_URL:
            rows = [{"Date": tpex_date, "SecuritiesCompanyCode": "00719B", "Close": "31.50"}]
        elif url in {TWSE_ACTION_SCHEDULE_URL, TPEX_ACTION_SCHEDULE_URL}:
            rows = []
        else:
            raise AssertionError(url)
        return _download(rows, url)
    return fetch


def test_discovers_and_prepares_next_date(tmp_path):
    primary = tmp_path / "0050.csv"
    defensive = tmp_path / "00719B.csv"
    _actions(primary)
    _actions(defensive)
    output = prepare_next_official_paper_bundle(
        _ledger(),
        primary_action_path=primary,
        defensive_action_path=defensive,
        output_root=tmp_path / "output",
        fetcher=_fetcher(),
    )
    loaded = load_official_paper_bundle(
        output, primary_action_path=primary, defensive_action_path=defensive
    )
    assert loaded.observed_on == date(2026, 7, 30)


def test_no_new_date_does_not_fetch_actions(tmp_path):
    calls = []
    fetch = _fetcher("1150729", "1150729")

    def tracked(url):
        calls.append(url)
        return fetch(url)

    assert prepare_next_official_paper_bundle(
        _ledger(),
        primary_action_path=tmp_path / "unused-a.csv",
        defensive_action_path=tmp_path / "unused-b.csv",
        output_root=tmp_path / "output",
        fetcher=tracked,
    ) is None
    assert calls == [TWSE_DAILY_CLOSE_URL, TPEX_DAILY_CLOSE_URL]


def test_mismatched_official_dates_leave_no_package(tmp_path):
    with pytest.raises(ValueError, match="not synchronized"):
        prepare_next_official_paper_bundle(
            _ledger(),
            primary_action_path=tmp_path / "unused-a.csv",
            defensive_action_path=tmp_path / "unused-b.csv",
            output_root=tmp_path / "output",
            fetcher=_fetcher("1150730", "1150729"),
        )
    assert not (tmp_path / "output" / "2026-07-30").exists()
