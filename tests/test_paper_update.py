from datetime import date

import pytest

from project_alpha.paper_tracking import CandidateSpec, PaperLedger, PaperObservation
from project_alpha.paper_update import (
    append_mark_to_market,
    append_scheduled_rebalance,
)


def spec(interval=63):
    return CandidateSpec(
        candidate_id="candidate",
        declared_on=date(2026, 7, 28),
        historical_cutoff=date(2026, 7, 27),
        primary_symbol="0050",
        defensive_symbol="00719B",
        primary_weight=0.6,
        defensive_weight=0.4,
        rebalance_interval_trading_days=interval,
    )


def initial_observation():
    return PaperObservation(
        observed_on=date(2026, 7, 28),
        portfolio_value=100.0,
        primary_close=1.0,
        defensive_close=1.0,
        primary_units=60,
        defensive_units=40,
        cash_balance=0.0,
        turnover_today=100.0,
        charged_transaction_costs_today=0.4,
    )


def test_non_rebalance_update_keeps_units_and_has_zero_turnover():
    ledger = PaperLedger(spec())
    ledger.append(initial_observation())
    result = append_mark_to_market(
        ledger,
        observed_on=date(2026, 7, 29),
        primary_close=1.1,
        defensive_close=0.9,
    )
    assert result.primary_units == 60
    assert result.defensive_units == 40
    assert result.portfolio_value == pytest.approx(102.0)
    assert result.turnover_today == 0.0
    assert result.charged_transaction_costs_today == 0.0


def test_distributions_are_credited_without_changing_units():
    ledger = PaperLedger(spec())
    ledger.append(initial_observation())
    result = append_mark_to_market(
        ledger,
        observed_on=date(2026, 7, 29),
        primary_close=0.9,
        defensive_close=0.98,
        primary_cash_dividend=0.1,
        defensive_cash_dividend=0.02,
    )
    assert result.cash_balance == pytest.approx(6.8)
    assert result.portfolio_value == pytest.approx(100.0)
    assert result.primary_units == 60
    assert result.defensive_units == 40


def test_initial_and_scheduled_rebalance_require_explicit_records():
    empty = PaperLedger(spec())
    with pytest.raises(ValueError, match="initial"):
        append_mark_to_market(
            empty,
            observed_on=date(2026, 7, 28),
            primary_close=1.0,
            defensive_close=1.0,
        )

    ledger = PaperLedger(spec(interval=2))
    ledger.append(initial_observation())
    append_mark_to_market(
        ledger,
        observed_on=date(2026, 7, 29),
        primary_close=1.0,
        defensive_close=1.0,
    )
    with pytest.raises(ValueError, match="scheduled rebalance"):
        append_mark_to_market(
            ledger,
            observed_on=date(2026, 7, 30),
            primary_close=1.0,
            defensive_close=1.0,
        )


@pytest.mark.parametrize("dividend", [-0.01, float("inf"), float("nan")])
def test_invalid_dividends_are_rejected(dividend):
    ledger = PaperLedger(spec())
    ledger.append(initial_observation())
    with pytest.raises(ValueError, match="dividends"):
        append_mark_to_market(
            ledger,
            observed_on=date(2026, 7, 29),
            primary_close=1.0,
            defensive_close=1.0,
            primary_cash_dividend=dividend,
        )


def test_scheduled_rebalance_restores_weights_and_charges_costs():
    ledger = PaperLedger(spec(interval=2))
    ledger.append(initial_observation())
    append_mark_to_market(
        ledger,
        observed_on=date(2026, 7, 29),
        primary_close=1.5,
        defensive_close=1.0,
    )
    result = append_scheduled_rebalance(
        ledger,
        observed_on=date(2026, 7, 30),
        primary_close=1.5,
        defensive_close=1.0,
    )
    assert result.turnover_today > 0
    assert result.charged_transaction_costs_today == pytest.approx(
        result.turnover_today * 0.004
    )
    assert abs(result.primary_weight - 0.6) <= 0.01
    assert abs(result.defensive_weight - 0.4) <= 0.01
    assert result.cash_balance >= 0


def test_in_tolerance_scheduled_observation_avoids_unnecessary_trade():
    ledger = PaperLedger(spec(interval=2))
    ledger.append(initial_observation())
    append_mark_to_market(
        ledger,
        observed_on=date(2026, 7, 29),
        primary_close=1.0,
        defensive_close=1.0,
    )
    result = append_scheduled_rebalance(
        ledger,
        observed_on=date(2026, 7, 30),
        primary_close=1.0,
        defensive_close=1.0,
    )
    assert result.primary_units == 60
    assert result.defensive_units == 40
    assert result.turnover_today == 0
    assert result.charged_transaction_costs_today == 0


def test_rebalance_is_rejected_off_schedule():
    ledger = PaperLedger(spec())
    ledger.append(initial_observation())
    with pytest.raises(ValueError, match="forbidden"):
        append_scheduled_rebalance(
            ledger,
            observed_on=date(2026, 7, 29),
            primary_close=1.0,
            defensive_close=1.0,
        )
