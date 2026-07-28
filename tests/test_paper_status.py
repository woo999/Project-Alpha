from datetime import date

from project_alpha.paper_status import build_paper_status
from project_alpha.paper_tracking import CandidateSpec, PaperLedger, PaperObservation


def ledger(interval=63):
    return PaperLedger(
        CandidateSpec(
            candidate_id="candidate",
            declared_on=date(2026, 7, 28),
            historical_cutoff=date(2026, 7, 27),
            primary_symbol="0050",
            defensive_symbol="00719B",
            primary_weight=0.6,
            defensive_weight=0.4,
            rebalance_interval_trading_days=interval,
        )
    )


def observation(day, price, *, turnover=0.0, cost=0.0):
    return PaperObservation(
        observed_on=day,
        portfolio_value=100 * price,
        primary_close=price,
        defensive_close=price,
        primary_units=60,
        defensive_units=40,
        cash_balance=0.0,
        turnover_today=turnover,
        charged_transaction_costs_today=cost,
    )


def test_status_reports_progress_weights_and_next_rebalance():
    target = ledger()
    target.append(
        observation(
            date(2026, 7, 28),
            1.0,
            turnover=100.0,
            cost=0.4,
        )
    )
    status = build_paper_status(target)
    assert status.observation_count == 1
    assert status.remaining_validation_observations == 251
    assert status.next_rebalance_observation == 64
    assert status.observations_until_next_rebalance == 63
    assert status.within_rebalance_tolerance is True
    assert status.live_ready is False


def test_status_raises_early_drawdown_warning():
    target = ledger()
    target.append(
        observation(
            date(2026, 7, 28),
            1.0,
            turnover=100.0,
            cost=0.4,
        )
    )
    target.append(observation(date(2026, 7, 29), 0.75))
    status = build_paper_status(target)
    assert status.maximum_drawdown == -0.25
    assert status.drawdown_limit_breached is True
    assert status.passed is False
