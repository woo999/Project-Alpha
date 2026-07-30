from datetime import date
import json

import pytest

from project_alpha.daily_official_close_evidence import (
    load_daily_official_close_evidence,
    prepare_daily_official_close_evidence,
)
from project_alpha.official_close import (
    TPEX_DAILY_CLOSE_URL,
    TWSE_DAILY_CLOSE_URL,
)
from project_alpha.official_source import OfficialSourceDownload


DAY = date(2026, 7, 29)


def _download(rows, url):
    return OfficialSourceDownload(
        json.dumps(rows).encode(),
        url,
        "application/json",
    )


def _fetcher(url):
    if url == TWSE_DAILY_CLOSE_URL:
        return _download(
            [{"Date": "1150729", "Code": "0050", "ClosingPrice": "93.70"}],
            url,
        )
    if url == TPEX_DAILY_CLOSE_URL:
        return _download(
            [
                {
                    "Date": "1150729",
                    "SecuritiesCompanyCode": "00719B",
                    "Close": "31.48",
                }
            ],
            url,
        )
    raise AssertionError(url)


def test_official_only_close_evidence_round_trip(tmp_path):
    output = prepare_daily_official_close_evidence(
        expected_date=DAY,
        output_root=tmp_path,
        fetcher=_fetcher,
    )
    loaded = load_daily_official_close_evidence(output)
    assert loaded.observed_on == DAY
    assert loaded.primary.close == pytest.approx(93.70)
    assert loaded.defensive.close == pytest.approx(31.48)


def test_tampered_official_close_is_rejected(tmp_path):
    output = prepare_daily_official_close_evidence(
        expected_date=DAY,
        output_root=tmp_path,
        fetcher=_fetcher,
    )
    (output / "0050_official_close.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        load_daily_official_close_evidence(output)


def test_date_mismatch_leaves_no_package(tmp_path):
    def stale_fetcher(url):
        if url == TWSE_DAILY_CLOSE_URL:
            return _download(
                [{"Date": "1150728", "Code": "0050", "ClosingPrice": "97.15"}],
                url,
            )
        return _fetcher(url)

    with pytest.raises(ValueError, match="dated 2026-07-28"):
        prepare_daily_official_close_evidence(
            expected_date=DAY,
            output_root=tmp_path,
            fetcher=stale_fetcher,
        )
    assert not (tmp_path / DAY.isoformat()).exists()
