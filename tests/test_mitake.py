from datetime import date

import pytest

from project_alpha.mitake import latest_common_bar, load_mitake_daily_export


def write_export(tmp_path, symbol, rows):
    path = tmp_path / f"{symbol}.txt"
    path.write_text(
        f"商品代碼:{symbol}\t商品名稱:test\n\n"
        "日期\t開盤價\t最高價\t最低價\t收盤價\t成交量\n"
        + "\n".join(rows)
        + "\n\n【資料來源：三竹股市電腦版】",
        encoding="utf-8-sig",
    )
    return path


def test_load_and_match_latest_common_date(tmp_path):
    primary = load_mitake_daily_export(
        write_export(
            tmp_path,
            "0050",
            [
                "'2026/07/27 00:00\t10\t11\t9\t10.5\t100",
                "'2026/07/28 00:00\t11\t12\t10\t11.5\t200",
            ],
        ),
        expected_symbol="0050",
    )
    defensive = load_mitake_daily_export(
        write_export(
            tmp_path,
            "00719B",
            [
                "'2026/07/27 00:00\t20\t21\t19\t20.5\t100",
                "'2026/07/28 00:00\t21\t22\t20\t21.5\t200",
            ],
        ),
        expected_symbol="00719B",
    )
    first, second = latest_common_bar(
        primary, defensive, after=date(2026, 7, 27)
    )
    assert first.observed_on == second.observed_on == date(2026, 7, 28)
    assert first.close == pytest.approx(11.5)
    assert second.close == pytest.approx(21.5)


@pytest.mark.parametrize(
    "rows,message",
    [
        (
            [
                "'2026/07/28 00:00\t11\t12\t10\t11.5\t200",
                "'2026/07/27 00:00\t10\t11\t9\t10.5\t100",
            ],
            "sorted",
        ),
        (
            [
                "'2026/07/27 00:00\t10\t11\t9\t10.5\t100",
                "'2026/07/27 00:00\t10\t11\t9\t10.5\t100",
            ],
            "duplicate",
        ),
        (["'2026/07/27 00:00\t10\t9\t8\t10.5\t100"], "OHLC"),
    ],
)
def test_unsafe_exports_are_rejected(tmp_path, rows, message):
    path = write_export(tmp_path, "0050", rows)
    with pytest.raises(ValueError, match=message):
        load_mitake_daily_export(path, expected_symbol="0050")


def test_wrong_symbol_and_missing_forward_date_are_rejected(tmp_path):
    path = write_export(
        tmp_path,
        "0050",
        ["'2026/07/27 00:00\t10\t11\t9\t10.5\t100"],
    )
    with pytest.raises(ValueError, match="expected symbol"):
        load_mitake_daily_export(path, expected_symbol="00719B")
    bars = load_mitake_daily_export(path, expected_symbol="0050")
    with pytest.raises(ValueError, match="no common date"):
        latest_common_bar(bars, bars, after=date(2026, 7, 27))
