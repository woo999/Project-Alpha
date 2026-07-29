from datetime import date
import json

import pytest

from project_alpha.action_schedule import (
    parse_tpex_action_schedule,
    parse_twse_action_schedule,
    verify_official_action_day,
)
from project_alpha.paper_daily import PaperAction


def test_twse_schedule_parses_roc_date_and_amounts():
    payload = json.dumps(
        [
            {
                "Date": "1150729",
                "Code": "0050",
                "StockDividendRatio": "",
                "CashDividend": "0.600000",
            }
        ]
    ).encode()
    item = parse_twse_action_schedule(payload)[0]
    assert item.event_date == date(2026, 7, 29)
    assert item.cash_dividend == pytest.approx(0.6)


def test_tpex_schedule_parses_chinese_schema():
    payload = json.dumps(
        [
            {
                "除權息日期": "115/07/29",
                "股票代號": "00719B",
                "無償配股率": "",
                "現金股利": "0.27",
            }
        ],
        ensure_ascii=False,
    ).encode()
    item = parse_tpex_action_schedule(payload)[0]
    assert item.symbol == "00719B"
    assert item.cash_dividend == pytest.approx(0.27)


def test_saved_schedule_must_agree_with_action_csv(tmp_path):
    source = tmp_path / "twse.json"
    source.write_text(
        json.dumps(
            [
                {
                    "Date": "1150729",
                    "Code": "0050",
                    "StockDividendRatio": "",
                    "CashDividend": "0.6",
                }
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="disagree"):
        verify_official_action_day(
            source,
            source_url="https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL",
            symbol="0050",
            event_date=date(2026, 7, 29),
            actions={},
        )
    verify_official_action_day(
        source,
        source_url="https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL",
        symbol="0050",
        event_date=date(2026, 7, 29),
        actions={date(2026, 7, 29): PaperAction(1.0, 0.6)},
    )
