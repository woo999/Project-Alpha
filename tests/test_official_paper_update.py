from datetime import date
import json

import pytest

from project_alpha.daily_action_evidence import prepare_daily_action_evidence
from project_alpha.daily_official_close_evidence import (
    prepare_daily_official_close_evidence,
)
from project_alpha.official_close import TPEX_DAILY_CLOSE_URL, TWSE_DAILY_CLOSE_URL
from project_alpha.official_paper_update import append_official_daily_mark
from project_alpha.official_source import OfficialSourceDownload
from project_alpha.paper_tracking import CandidateSpec, PaperLedger, PaperObservation


DAY = date(2026, 7, 29)


def _download(rows, url):
    return OfficialSourceDownload(json.dumps(rows).encode(), url, "application/json")


def _fetcher(url):
    if url == TWSE_DAILY_CLOSE_URL:
        rows = [{"Date": "1150729", "Code": "0050", "ClosingPrice": "93.70"}]
    elif url == TPEX_DAILY_CLOSE_URL:
        rows = [{"Date": "1150729", "SecuritiesCompanyCode": "00719B", "Close": "31.48"}]
    elif "TWT48U_ALL" in url:
        rows = []
    elif "tpex_exright_prepost" in url:
        rows = []
    else:
        raise AssertionError(url)
    return _download(rows, url)


def _ledger():
    result = PaperLedger(
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
    result.append(
        PaperObservation(
            observed_on=date(2026, 7, 28),
            portfolio_value=298804.841,
            primary_close=97.15,
            defensive_close=31.46,
            primary_units=1845,
            defensive_units=3800,
            cash_balance=15.091,
        )
    )
    return result


def _actions(path):
    path.write_text("date,split_ratio,cash_dividend\n2026-07-21,1,0\n", encoding="utf-8")


def test_official_evidence_appends_one_mark(tmp_path):
    primary_actions = tmp_path / "0050.csv"
    defensive_actions = tmp_path / "00719B.csv"
    _actions(primary_actions)
    _actions(defensive_actions)
    close_dir = prepare_daily_official_close_evidence(
        expected_date=DAY, output_root=tmp_path / "close", fetcher=_fetcher
    )
    action_dir = prepare_daily_action_evidence(
        verified_through=DAY,
        primary_action_path=primary_actions,
        defensive_action_path=defensive_actions,
        output_root=tmp_path / "actions",
        fetcher=_fetcher,
    )
    ledger = _ledger()
    audit = append_official_daily_mark(
        ledger,
        close_evidence_dir=close_dir,
        action_evidence_dir=action_dir,
        primary_actions_path=primary_actions,
        defensive_actions_path=defensive_actions,
    )
    assert len(ledger.observations) == 2
    assert ledger.observations[-1].observed_on == DAY
    assert ledger.observations[-1].primary_close == pytest.approx(93.70)
    assert audit["safety"]["orders_placed"] is False


def test_mismatched_evidence_dates_leave_ledger_unchanged(tmp_path):
    primary_actions = tmp_path / "0050.csv"
    defensive_actions = tmp_path / "00719B.csv"
    _actions(primary_actions)
    _actions(defensive_actions)
    close_dir = prepare_daily_official_close_evidence(
        expected_date=DAY, output_root=tmp_path / "close", fetcher=_fetcher
    )
    action_dir = prepare_daily_action_evidence(
        verified_through=date(2026, 7, 28),
        primary_action_path=primary_actions,
        defensive_action_path=defensive_actions,
        output_root=tmp_path / "actions",
        fetcher=_fetcher,
    )
    ledger = _ledger()
    with pytest.raises(ValueError, match="dates do not match"):
        append_official_daily_mark(
            ledger,
            close_evidence_dir=close_dir,
            action_evidence_dir=action_dir,
            primary_actions_path=primary_actions,
            defensive_actions_path=defensive_actions,
        )
    assert len(ledger.observations) == 1
