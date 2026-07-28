from datetime import date

import pytest

from project_alpha.mitake import MitakeDailyBar, common_bars_after


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
