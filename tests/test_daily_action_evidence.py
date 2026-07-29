from datetime import date
import json

import pytest

from project_alpha.daily_action_evidence import (
    TPEX_ACTION_SCHEDULE_URL,
    TWSE_ACTION_SCHEDULE_URL,
    load_daily_action_evidence,
    prepare_daily_action_evidence,
)
from project_alpha.official_source import OfficialSourceDownload


def _actions(path):
    path.write_text(
        "date,split_ratio,cash_dividend\n"
        "2026-01-01,1.0,0.1\n",
        encoding="utf-8",
    )


def _fake_fetcher(*, primary_cash=0.0):
    def fetch(url):
        if url == TWSE_ACTION_SCHEDULE_URL:
            rows = (
                []
                if primary_cash == 0
                else [
                    {
                        "Date": "1150729",
                        "Code": "0050",
                        "StockDividendRatio": "",
                        "CashDividend": str(primary_cash),
                    }
                ]
            )
        elif url == TPEX_ACTION_SCHEDULE_URL:
            rows = []
        else:
            raise AssertionError("unexpected URL")
        return OfficialSourceDownload(
            json.dumps(rows).encode(),
            url,
            "application/json",
        )

    return fetch


def test_daily_evidence_is_published_as_one_complete_directory(tmp_path):
    primary = tmp_path / "0050.csv"
    defensive = tmp_path / "00719B.csv"
    _actions(primary)
    _actions(defensive)
    output = prepare_daily_action_evidence(
        verified_through=date(2026, 7, 29),
        primary_action_path=primary,
        defensive_action_path=defensive,
        output_root=tmp_path / "evidence",
        fetcher=_fake_fetcher(),
    )
    assert {item.name for item in output.iterdir()} == {
        "0050_official_schedule.json",
        "00719B_official_schedule.json",
        "0050_action_verification.json",
        "00719B_action_verification.json",
        "manifest.json",
    }
    assert json.loads((output / "manifest.json").read_text())[
        "verified_through"
    ] == "2026-07-29"
    loaded = load_daily_action_evidence(
        output,
        primary_action_path=primary,
        defensive_action_path=defensive,
    )
    assert loaded.verified_through == date(2026, 7, 29)


def test_conflict_leaves_no_partial_daily_directory(tmp_path):
    primary = tmp_path / "0050.csv"
    defensive = tmp_path / "00719B.csv"
    _actions(primary)
    _actions(defensive)
    root = tmp_path / "evidence"
    with pytest.raises(ValueError, match="disagree"):
        prepare_daily_action_evidence(
            verified_through=date(2026, 7, 29),
            primary_action_path=primary,
            defensive_action_path=defensive,
            output_root=root,
            fetcher=_fake_fetcher(primary_cash=0.6),
        )
    assert not (root / "2026-07-29").exists()
    assert not tuple(root.glob(".action-evidence-*"))


def test_existing_daily_evidence_cannot_be_overwritten(tmp_path):
    primary = tmp_path / "0050.csv"
    defensive = tmp_path / "00719B.csv"
    _actions(primary)
    _actions(defensive)
    root = tmp_path / "evidence"
    (root / "2026-07-29").mkdir(parents=True)
    with pytest.raises(FileExistsError):
        prepare_daily_action_evidence(
            verified_through=date(2026, 7, 29),
            primary_action_path=primary,
            defensive_action_path=defensive,
            output_root=root,
            fetcher=_fake_fetcher(),
        )


def test_tampered_or_misdated_package_is_rejected(tmp_path):
    primary = tmp_path / "0050.csv"
    defensive = tmp_path / "00719B.csv"
    _actions(primary)
    _actions(defensive)
    output = prepare_daily_action_evidence(
        verified_through=date(2026, 7, 29),
        primary_action_path=primary,
        defensive_action_path=defensive,
        output_root=tmp_path / "evidence",
        fetcher=_fake_fetcher(),
    )
    (output / "0050_official_schedule.json").write_text("[{}]")
    with pytest.raises(ValueError, match="manifest"):
        load_daily_action_evidence(
            output,
            primary_action_path=primary,
            defensive_action_path=defensive,
        )
