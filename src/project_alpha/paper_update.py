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


def append_scheduled_rebalance(
    ledger: PaperLedger,
    *,
    observed_on: date,
    primary_close: float,
    defensive_close: float,
    primary_cash_dividend: float = 0.0,
    defensive_cash_dividend: float = 0.0,
) -> PaperObservation:
    """Rebalance a scheduled observation to the frozen weights.

    The search uses integer units, charges the frozen minimum cost rate on
    gross two-sided turnover, and refuses any result with negative cash.  If
    the marked portfolio is already within tolerance, no trade is recorded.
    """
    if not ledger.observations:
        raise ValueError("initial paper allocation must be recorded explicitly")
    observation_number = len(ledger.observations) + 1
    if not ledger.spec.is_rebalance_observation(observation_number):
        raise ValueError("rebalance is forbidden outside scheduled observations")
    dividends = (primary_cash_dividend, defensive_cash_dividend)
    if any(not math.isfinite(value) or value < 0 for value in dividends):
        raise ValueError("cash dividends must be finite and non-negative")
    if any(
        not math.isfinite(value) or value <= 0
        for value in (primary_close, defensive_close)
    ):
        raise ValueError("rebalance closes must be finite and positive")

    previous = ledger.observations[-1]
    cash_before = (
        previous.cash_balance
        + previous.primary_units * primary_cash_dividend
        + previous.defensive_units * defensive_cash_dividend
    )
    value_before = (
        previous.primary_units * primary_close
        + previous.defensive_units * defensive_close
        + cash_before
    )
    no_trade = PaperObservation(
        observed_on=observed_on,
        portfolio_value=value_before,
        primary_close=primary_close,
        defensive_close=defensive_close,
        primary_units=previous.primary_units,
        defensive_units=previous.defensive_units,
        cash_balance=cash_before,
    )
    tolerance = ledger.spec.rebalance_weight_tolerance
    if (
        abs(no_trade.primary_weight - ledger.spec.primary_weight) <= tolerance
        and abs(no_trade.defensive_weight - ledger.spec.defensive_weight)
        <= tolerance
        and no_trade.cash_weight <= tolerance
    ):
        ledger.append(no_trade)
        return no_trade

    primary_ideal = value_before * ledger.spec.primary_weight / primary_close
    defensive_ideal = (
        value_before * ledger.spec.defensive_weight / defensive_close
    )
    primary_candidates = range(
        max(0, round(primary_ideal) - 50),
        round(primary_ideal) + 51,
    )
    defensive_candidates = range(
        max(0, round(defensive_ideal) - 50),
        round(defensive_ideal) + 51,
    )
    best: tuple[tuple[float, float, float], PaperObservation] | None = None
    for primary_units in primary_candidates:
        for defensive_units in defensive_candidates:
            primary_delta = primary_units - previous.primary_units
            defensive_delta = defensive_units - previous.defensive_units
            turnover = (
                abs(primary_delta) * primary_close
                + abs(defensive_delta) * defensive_close
            )
            costs = turnover * ledger.spec.minimum_transaction_cost_rate
            cash_after = (
                cash_before
                - primary_delta * primary_close
                - defensive_delta * defensive_close
                - costs
            )
            if cash_after < 0:
                continue
            portfolio_value = (
                primary_units * primary_close
                + defensive_units * defensive_close
                + cash_after
            )
            candidate = PaperObservation(
                observed_on=observed_on,
                portfolio_value=portfolio_value,
                primary_close=primary_close,
                defensive_close=defensive_close,
                primary_units=primary_units,
                defensive_units=defensive_units,
                cash_balance=cash_after,
                turnover_today=turnover,
                charged_transaction_costs_today=costs,
            )
            deviations = (
                abs(candidate.primary_weight - ledger.spec.primary_weight),
                abs(candidate.defensive_weight - ledger.spec.defensive_weight),
                candidate.cash_weight,
            )
            if max(deviations) > tolerance:
                continue
            score = (max(deviations), turnover, cash_after)
            if best is None or score < best[0]:
                best = (score, candidate)
    if best is None:
        raise ValueError(
            "no integer rebalance satisfies frozen weights, costs, and cash limits"
        )
    ledger.append(best[1])
    return best[1]
