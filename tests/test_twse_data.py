import pytest

from project_alpha.twse_data import parse_taiwan50_payload


def test_parse_official_taiwan50_payload():
    payload = {
        "stat": "OK",
        "fields": ["日期", "臺灣50指數", "臺灣50報酬指數"],
        "data": [
            ["109/01/02", "9,450.90", "17,849.79"],
            ["109/01/03", "9,475.62", "17,896.47"],
        ],
    }

    result = parse_taiwan50_payload(payload)

    assert result.index[0].isoformat() == "2020-01-02T00:00:00"
    assert result["price_index"].tolist() == [9450.90, 9475.62]
    assert result["close"].tolist() == [17849.79, 17896.47]


def test_parse_rejects_changed_response_schema():
    with pytest.raises(ValueError, match="fields changed"):
        parse_taiwan50_payload(
            {
                "stat": "OK",
                "fields": ["date", "close"],
                "data": [["2020-01-02", "100"]],
            }
        )
