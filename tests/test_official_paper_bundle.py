from datetime import date
import json

import pytest

from project_alpha.daily_action_evidence import (
    TPEX_ACTION_SCHEDULE_URL,
    TWSE_ACTION_SCHEDULE_URL,
)
from project_alpha.official_close import TPEX_DAILY_CLOSE_URL, TWSE_DAILY_CLOSE_URL
from project_alpha.official_paper_bundle import (
    load_official_paper_bundle,
    prepare_official_paper_bundle,
)
from project_alpha.official_source import OfficialSourceDownload


DAY = date(2026, 7, 29)


def _download(rows, url):
    return OfficialSourceDownload(json.dumps(rows).encode(), url, "application/json")


def _fetcher(url):
    if url == TWSE_DAILY_CLOSE_URL:
        rows = [{"Date": "1150729", "Code": "0050", "ClosingPrice": "93.70"}]
    elif url == TPEX_DAILY_CLOSE_URL:
        rows = [{"Date": "1150729", "SecuritiesCompanyCode": "00719B", "Close": "31.48"}]
    elif url in {TWSE_ACTION_SCHEDULE_URL, TPEX_ACTION_SCHEDULE_URL}:
        rows = []
    else:
        raise AssertionError(url)
    return _download(rows, url)


def _actions(path):
    path.write_text("date,split_ratio,cash_dividend\n2026-07-21,1,0\n", encoding="utf-8")


def test_four_source_bundle_round_trip(tmp_path):
    primary = tmp_path / "0050.csv"
    defensive = tmp_path / "00719B.csv"
    _actions(primary)
    _actions(defensive)
    output = prepare_official_paper_bundle(
        observed_on=DAY,
        primary_action_path=primary,
        defensive_action_path=defensive,
        output_root=tmp_path / "output",
        fetcher=_fetcher,
    )
    loaded = load_official_paper_bundle(
        output,
        primary_action_path=primary,
        defensive_action_path=defensive,
    )
    assert loaded.observed_on == DAY
    assert loaded.close.primary.close == pytest.approx(93.70)


def test_failure_leaves_no_partial_bundle(tmp_path):
    primary = tmp_path / "0050.csv"
    defensive = tmp_path / "00719B.csv"
    _actions(primary)
    _actions(defensive)

    def fail_last(url):
        if url == TPEX_ACTION_SCHEDULE_URL:
            raise TimeoutError("simulated official timeout")
        return _fetcher(url)

    output_root = tmp_path / "output"
    with pytest.raises(TimeoutError):
        prepare_official_paper_bundle(
            observed_on=DAY,
            primary_action_path=primary,
            defensive_action_path=defensive,
            output_root=output_root,
            fetcher=fail_last,
        )
    assert not (output_root / DAY.isoformat()).exists()
