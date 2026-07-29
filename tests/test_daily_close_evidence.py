import json

import pytest

from project_alpha.daily_close_evidence import (
    load_daily_close_evidence,
    prepare_daily_close_evidence,
)
from project_alpha.official_close import (
    TPEX_DAILY_CLOSE_URL,
    TWSE_DAILY_CLOSE_URL,
)
from project_alpha.official_source import OfficialSourceDownload


def _export(path, symbol, day, close):
    path.write_text(
        f"商品代碼:{symbol}\t商品名稱:test\n\n"
        "日期\t開盤價\t最高價\t最低價\t收盤價\t成交量\n"
        f"'{day} 00:00\t{close}\t{close}\t{close}\t{close}\t100\n",
        encoding="utf-8-sig",
    )


def _fetcher(primary_close=98.15):
    def fetch(url):
        if url == TWSE_DAILY_CLOSE_URL:
            rows = [
                {
                    "Date": "1150729",
                    "Code": "0050",
                    "ClosingPrice": str(primary_close),
                }
            ]
        elif url == TPEX_DAILY_CLOSE_URL:
            rows = [
                {"資料日期": "1150729", "代號": "00719B", "收盤": "31.5"}
            ]
        else:
            raise AssertionError("unexpected URL")
        return OfficialSourceDownload(
            json.dumps(rows, ensure_ascii=False).encode(),
            url,
            "application/json",
        )

    return fetch


def test_close_evidence_is_published_atomically(tmp_path):
    primary = tmp_path / "0050.txt"
    defensive = tmp_path / "00719B.txt"
    _export(primary, "0050", "2026/07/29", 98.15)
    _export(defensive, "00719B", "2026/07/29", 31.5)
    output = prepare_daily_close_evidence(
        primary_export_path=primary,
        defensive_export_path=defensive,
        output_root=tmp_path / "evidence",
        fetcher=_fetcher(),
    )
    assert {item.name for item in output.iterdir()} == {
        "0050_official_close.json",
        "00719B_official_close.json",
        "manifest.json",
    }
    loaded = load_daily_close_evidence(
        output,
        primary_export_path=primary,
        defensive_export_path=defensive,
    )
    assert loaded.observed_on.isoformat() == "2026-07-29"


def test_close_conflict_leaves_no_partial_package(tmp_path):
    primary = tmp_path / "0050.txt"
    defensive = tmp_path / "00719B.txt"
    _export(primary, "0050", "2026/07/29", 98.15)
    _export(defensive, "00719B", "2026/07/29", 31.5)
    root = tmp_path / "evidence"
    with pytest.raises(ValueError, match="conflicts"):
        prepare_daily_close_evidence(
            primary_export_path=primary,
            defensive_export_path=defensive,
            output_root=root,
            fetcher=_fetcher(primary_close=98.10),
        )
    assert not (root / "2026-07-29").exists()
    assert not tuple(root.glob(".close-evidence-*"))


def test_asymmetric_latest_dates_are_rejected_before_download(tmp_path):
    primary = tmp_path / "0050.txt"
    defensive = tmp_path / "00719B.txt"
    _export(primary, "0050", "2026/07/29", 98.15)
    _export(defensive, "00719B", "2026/07/28", 31.5)
    with pytest.raises(ValueError, match="different latest dates"):
        prepare_daily_close_evidence(
            primary_export_path=primary,
            defensive_export_path=defensive,
            output_root=tmp_path / "evidence",
            fetcher=_fetcher(),
        )


def test_modified_export_or_official_source_is_rejected(tmp_path):
    primary = tmp_path / "0050.txt"
    defensive = tmp_path / "00719B.txt"
    _export(primary, "0050", "2026/07/29", 98.15)
    _export(defensive, "00719B", "2026/07/29", 31.5)
    output = prepare_daily_close_evidence(
        primary_export_path=primary,
        defensive_export_path=defensive,
        output_root=tmp_path / "evidence",
        fetcher=_fetcher(),
    )
    primary.write_text(primary.read_text().replace("98.15", "98.10"))
    with pytest.raises(ValueError, match="export"):
        load_daily_close_evidence(
            output,
            primary_export_path=primary,
            defensive_export_path=defensive,
        )
