from datetime import date

import pytest

from project_alpha.tpex_exright import parse_tpex_exright_payload


FIELDS = ["除權息日期", "代號", "名稱", "現金股利"]


def payload(rows):
    return {
        "stat": "ok",
        "tables": [{"fields": FIELDS, "data": rows}],
    }


def test_extracts_one_strict_official_distribution():
    record = parse_tpex_exright_payload(
        payload([["108/01/22", "00719B", "元大美債1-3", "0.08000000"]]),
        symbol="00719B",
        expected_date=date(2019, 1, 22),
    )
    assert record.ex_date == date(2019, 1, 22)
    assert record.cash_dividend == pytest.approx(0.08)


def test_rejects_schema_change_or_duplicate_match():
    with pytest.raises(ValueError, match="fields changed"):
        parse_tpex_exright_payload(
            {"stat": "ok", "tables": [{"fields": ["代號"], "data": []}]},
            symbol="00719B",
            expected_date=date(2019, 1, 22),
        )
    duplicate = ["108/01/22", "00719B", "元大美債1-3", "0.08"]
    with pytest.raises(ValueError, match="found 2"):
        parse_tpex_exright_payload(
            payload([duplicate, duplicate]),
            symbol="00719B",
            expected_date=date(2019, 1, 22),
        )
