from datetime import date

import pytest

from project_alpha.mitake import MitakeDailyBar
from project_alpha.paper_daily import (
    PaperAction,
    append_common_daily_bars,
    load_paper_actions,
    validate_action_freshness,
)
from project_alpha.paper_tracking import CandidateSpec, PaperLedger, PaperObservation


def bar(observed_on, close):
    return MitakeDailyBar(observed_on, close, close, close, close, 1)


def ledger(interval=63):
    spec = CandidateSpec(
        candidate_id="candidate",
        declared_on=date(2026, 7, 28),
        historical_cutoff=date(2026, 7, 27),
        primary_symbol="0050",
        defensive_symbol="00719B",
        primary_weight=0.6,
        defensive_weight=0.4,
        rebalance_interval_trading_days=interval,
    )
    result = PaperLedger(spec)
    result.append(
        PaperObservation(
            observed_on=date(2026, 7, 28),
            portfolio_value=99.6,
            primary_close=1,
            defensive_close=1,
            primary_units=60,
            defensive_units=39,
            cash_balance=0.6,
            turnover_today=99,
            charged_transaction_costs_today=0.396,
        )
    )
    return result


def test_batch_update_credits_dividend_and_stops_before_rebalance():
    target = ledger(interval=2)
    pairs = (
        (bar(date(2026, 7, 29), 1.0), bar(date(2026, 7, 29), 1.0)),
        (bar(date(2026, 7, 30), 1.0), bar(date(2026, 7, 30), 1.0)),
    )
    result = append_common_daily_bars(
        target,
        pairs,
        primary_actions={date(2026, 7, 29): PaperAction(1.0, 0.1)},
        defensive_actions={},
    )
    assert result.appended_dates == (date(2026, 7, 29),)
    assert result.stopped_before_rebalance is True
    assert target.observations[-1].cash_balance == pytest.approx(6.6)


def test_split_is_rejected():
    target = ledger()
    pairs = ((bar(date(2026, 7, 29), 1.0), bar(date(2026, 7, 29), 1.0)),)
    with pytest.raises(ValueError, match="explicit unit adjustment"):
        append_common_daily_bars(
            target,
            pairs,
            primary_actions={date(2026, 7, 29): PaperAction(4.0, 0.0)},
            defensive_actions={},
        )


def test_action_file_is_strict(tmp_path):
    path = tmp_path / "actions.csv"
    path.write_text(
        "date,split_ratio,cash_dividend\n"
        "2026-07-29,1,0.1\n"
        "2026-07-28,1,0.2\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="chronological"):
        load_paper_actions(path)


def test_stale_action_coverage_is_rejected():
    actions = {date(2026, 7, 21): PaperAction(1.0, 0.6)}
    with pytest.raises(ValueError, match="before required market date"):
        validate_action_freshness(
            actions,
            verified_through=date(2026, 7, 28),
            required_through=date(2026, 7, 29),
            label="0050",
        )
    validate_action_freshness(
        actions,
        verified_through=date(2026, 7, 29),
        required_through=date(2026, 7, 29),
        label="0050",
    )
