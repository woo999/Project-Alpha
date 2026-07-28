"""Safe mark-to-market updates for an active offline paper ledger."""

from __future__ import annotations

from datetime import date
import math

from project_alpha.paper_tracking import PaperLedger, PaperObservation


def append_mark_to_market(
    ledger: PaperLedger,
    *,
    observed_on: date,
    primary_close: float,
    defensive_close: float,
    primary_cash_dividend: float = 0.0,
    defensive_cash_dividend: float = 0.0,
) -> PaperObservation:
    """Append one non-rebalance close without permitting hidden trading.

    Cash distributions are recognized on the supplied event date for
    total-return accounting.  This function deliberately refuses observation
    1 and every scheduled rebalance observation; those require an explicit
    allocation record including turnover and charged costs.
    """
    if not ledger.observations:
        raise ValueError("initial paper allocation must be recorded explicitly")
    observation_number = len(ledger.observations) + 1
    if ledger.spec.is_rebalance_observation(observation_number):
        raise ValueError(
            "scheduled rebalance observation requires explicit allocation"
        )
    dividends = (primary_cash_dividend, defensive_cash_dividend)
    if any(not math.isfinite(value) or value < 0 for value in dividends):
        raise ValueError("cash dividends must be finite and non-negative")

    previous = ledger.observations[-1]
    cash_balance = (
        previous.cash_balance
        + previous.primary_units * primary_cash_dividend
        + previous.defensive_units * defensive_cash_dividend
    )
    portfolio_value = (
        previous.primary_units * primary_close
        + previous.defensive_units * defensive_close
        + cash_balance
    )
    observation = PaperObservation(
        observed_on=observed_on,
        portfolio_value=portfolio_value,
        primary_close=primary_close,
        defensive_close=defensive_close,
        primary_units=previous.primary_units,
        defensive_units=previous.defensive_units,
        cash_balance=cash_balance,
        turnover_today=0.0,
        charged_transaction_costs_today=0.0,
    )
    ledger.append(observation)
    return observation
