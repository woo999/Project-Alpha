from datetime import date
import json

import pytest

from project_alpha.official_close import (
    TPEX_DAILY_CLOSE_URL,
    TWSE_DAILY_CLOSE_URL,
    parse_tpex_daily_closes,
    parse_twse_daily_closes,
    verify_official_close,
)


def test_twse_close_parses_roc_date_and_price():
    payload = json.dumps(
        [{"Date": "1150729", "Code": "0050", "ClosingPrice": "98.15"}]
    ).encode()
    row = parse_twse_daily_closes(payload)[0]
    assert row.observed_on == date(2026, 7, 29)
    assert row.close == pytest.approx(98.15)


def test_tpex_close_parses_chinese_schema():
    payload = json.dumps(
        [{"資料日期": "115/07/29", "代號": "00719B", "收盤": "31.50"}],
        ensure_ascii=False,
    ).encode()
    row = parse_tpex_daily_closes(payload)[0]
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
            [{"資料日期": "1150729", "代號": "00719B", "收盤": "31.5"}],
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
