from datetime import date

import pytest

from project_alpha.mitake import (
    MitakeDailyBar,
    common_bars_after,
    single_common_bar_after,
)


def bar(day):
    return MitakeDailyBar(day, 1, 1, 1, 1, 1)


def test_common_bars_after_returns_every_common_date():
    primary = (
        bar(date(2026, 7, 28)),
        bar(date(2026, 7, 30)),
    )
    defensive = (
        bar(date(2026, 7, 28)),
        bar(date(2026, 7, 30)),
    )
    result = common_bars_after(primary, defensive, after=date(2026, 7, 27))
    assert [pair[0].observed_on for pair in result] == [
        date(2026, 7, 28),
        date(2026, 7, 30),
    ]


def test_common_bars_after_rejects_asymmetric_exports():
    primary = (
        bar(date(2026, 7, 28)),
        bar(date(2026, 7, 29)),
    )
    defensive = (bar(date(2026, 7, 28)),)
    with pytest.raises(ValueError, match="asymmetric"):
        common_bars_after(primary, defensive, after=date(2026, 7, 27))


def test_single_common_bar_requires_exactly_the_expected_new_date():
    primary = (
        bar(date(2026, 7, 28)),
        bar(date(2026, 7, 29)),
        bar(date(2026, 7, 30)),
    )
    defensive = primary
    with pytest.raises(
        ValueError,
        match=r"must be exactly \[2026-07-30\].*2026-07-29",
    ):
        single_common_bar_after(
            primary,
            defensive,
            after=date(2026, 7, 28),
            expected_date=date(2026, 7, 30),
        )


def test_single_common_bar_accepts_one_expected_new_date():
    primary = (
        bar(date(2026, 7, 28)),
        bar(date(2026, 7, 29)),
    )
    defensive = primary
    result = single_common_bar_after(
        primary,
        defensive,
        after=date(2026, 7, 28),
        expected_date=date(2026, 7, 29),
    )
    assert result[0].observed_on == date(2026, 7, 29)
