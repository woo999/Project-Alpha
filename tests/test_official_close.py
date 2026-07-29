from datetime import date
import json

import pytest

from project_alpha.official_close import (
    TPEX_DAILY_CLOSE_URL,
    TWSE_DAILY_CLOSE_URL,
    OfficialClose,
    close_readiness_blockers,
    parse_tpex_daily_closes,
    parse_twse_daily_closes,
    official_close_for_symbol,
    verify_official_close,
)


def test_twse_close_parses_roc_date_and_price():
    payload = json.dumps(
        [
            {"Date": "1150729", "Code": "00682U", "ClosingPrice": ""},
            {"Date": "1150729", "Code": "0050", "ClosingPrice": "98.15"},
        ]
    ).encode()
    rows = parse_twse_daily_closes(payload)
    assert len(rows) == 1
    row = rows[0]
    assert row.observed_on == date(2026, 7, 29)
    assert row.close == pytest.approx(98.15)


def test_tpex_close_parses_current_openapi_schema():
    payload = json.dumps(
        [
            {
                "Date": "115/07/29",
                "SecuritiesCompanyCode": "006201",
                "Close": "---",
            },
            {
                "Date": "115/07/29",
                "SecuritiesCompanyCode": "00719B",
                "Close": "31.50",
            }
        ],
        ensure_ascii=False,
    ).encode()
    rows = parse_tpex_daily_closes(payload)
    assert len(rows) == 1
    row = rows[0]
    assert row.symbol == "00719B"
    assert row.close == pytest.approx(31.5)


@pytest.mark.parametrize(
    "rows,url,symbol,close",
    [
        (
            [{"Date": "1150729", "Code": "0050", "ClosingPrice": "98.15"}],
            TWSE_DAILY_CLOSE_URL,
            "0050",
            98.10,
        ),
        (
            [
                {
                    "Date": "1150729",
                    "SecuritiesCompanyCode": "00719B",
                    "Close": "31.5",
                }
            ],
            TPEX_DAILY_CLOSE_URL,
            "00719B",
            31.4,
        ),
    ],
)
def test_close_conflict_is_rejected(rows, url, symbol, close):
    with pytest.raises(ValueError, match="conflicts"):
        verify_official_close(
            json.dumps(rows, ensure_ascii=False).encode(),
            source_url=url,
            symbol=symbol,
            expected_date=date(2026, 7, 29),
            expected_close=close,
        )


def test_missing_or_duplicate_symbol_date_is_rejected():
    row = {"Date": "1150729", "Code": "0050", "ClosingPrice": "98.15"}
    with pytest.raises(ValueError, match="exactly one"):
        verify_official_close(
            json.dumps([row, row]).encode(),
            source_url=TWSE_DAILY_CLOSE_URL,
            symbol="0050",
            expected_date=date(2026, 7, 29),
            expected_close=98.15,
        )


def test_date_mismatch_reports_available_official_date():
    rows = [{"Date": "1150728", "Code": "0050", "ClosingPrice": "97.15"}]
    with pytest.raises(
        ValueError,
        match="dated 2026-07-28, expected 2026-07-29",
    ):
        verify_official_close(
            json.dumps(rows).encode(),
            source_url=TWSE_DAILY_CLOSE_URL,
            symbol="0050",
            expected_date=date(2026, 7, 29),
            expected_close=98.15,
        )


def test_symbol_lookup_is_independent_of_expected_date():
    rows = [{"Date": "1150728", "Code": "0050", "ClosingPrice": "97.15"}]
    result = official_close_for_symbol(
        json.dumps(rows).encode(),
        source_url=TWSE_DAILY_CLOSE_URL,
        symbol="0050",
    )
    assert result.observed_on == date(2026, 7, 28)
    assert result.close == pytest.approx(97.15)


def test_readiness_reports_official_export_dates_and_price_conflict():
    expected = date(2026, 7, 29)
    blockers = close_readiness_blockers(
        expected_date=expected,
        official_closes={
            "0050": OfficialClose(date(2026, 7, 28), "0050", 97.15),
            "00719B": OfficialClose(expected, "00719B", 31.48),
        },
        export_closes={
            "0050": OfficialClose(date(2026, 7, 28), "0050", 97.15),
            "00719B": OfficialClose(expected, "00719B", 31.46),
        },
    )
    assert blockers == (
        "0050 official date is 2026-07-28, expected 2026-07-29",
        "0050 Mitake date is 2026-07-28, expected 2026-07-29",
        "00719B Mitake close conflicts with official close",
    )


def test_readiness_accepts_matching_official_and_export_closes():
    expected = date(2026, 7, 29)
    closes = {
        "0050": OfficialClose(expected, "0050", 98.15),
        "00719B": OfficialClose(expected, "00719B", 31.48),
    }
    assert (
        close_readiness_blockers(
            expected_date=expected,
            official_closes=closes,
            export_closes=closes,
        )
        == ()
    )
