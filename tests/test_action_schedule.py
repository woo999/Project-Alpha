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


def test_tpex_schedule_parses_current_openapi_schema():
    payload = json.dumps(
        [
            {
                "ExRrightsExDividendDate": "115/07/29",
                "SecuritiesCompanyCode": "00719B",
                "StockDividendRatio": "",
                "CashDividend": "0.27",
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


def test_unannounced_cash_dividend_cannot_verify_action_csv(tmp_path):
    source = tmp_path / "tpex.json"
    source.write_text(
        json.dumps(
            [
                {
                    "ExRrightsExDividendDate": "1150731",
                    "SecuritiesCompanyCode": "00719B",
                    "StockDividendRatio": "0.00000000",
                    "CashDividend": "尚未公告",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not yet announced"):
        verify_official_action_day(
            source,
            source_url=(
                "https://www.tpex.org.tw/openapi/v1/"
                "tpex_exright_prepost"
            ),
            symbol="00719B",
            event_date=date(2026, 7, 31),
            actions={date(2026, 7, 31): PaperAction(1.0, 0.27)},
        )


def test_other_official_path_cannot_verify_action_schedule(tmp_path):
    source = tmp_path / "wrong-endpoint.json"
    source.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported"):
        verify_official_action_day(
            source,
            source_url="https://www.tpex.org.tw/openapi/v1/tpex_cmode",
            symbol="00719B",
            event_date=date(2026, 7, 29),
            actions={},
        )
