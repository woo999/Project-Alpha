"""Read-only status reporting for an authenticated offline paper ledger."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from project_alpha.paper_tracking import PaperLedger


@dataclass(frozen=True)
class PaperStatus:
    candidate_id: str
    mode: str
    live_ready: bool
    observation_count: int
    remaining_validation_observations: int
    last_observed_on: date
    portfolio_value: float
    primary_weight: float
    defensive_weight: float
    cash_weight: float
    primary_weight_deviation: float
    defensive_weight_deviation: float
    within_rebalance_tolerance: bool
    allocation_drift_outside_tolerance: bool
    rebalance_due_next_observation: bool
    next_rebalance_observation: int
    observations_until_next_rebalance: int
    cumulative_return: float | None
    maximum_drawdown: float | None
    maximum_drawdown_limit: float
    drawdown_limit_breached: bool
    eligible: bool
    passed: bool
    reasons: tuple[str, ...]
    ledger_hash: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_paper_status(ledger: PaperLedger) -> PaperStatus:
    """Build a decision-oriented report without changing the ledger."""
    if not ledger.observations:
        raise ValueError("paper status requires at least one observation")
    count = len(ledger.observations)
    next_rebalance = count + 1
    while not ledger.spec.is_rebalance_observation(next_rebalance):
        next_rebalance += 1
    latest = ledger.observations[-1]
    decision = ledger.evaluate()
    primary_deviation = latest.primary_weight - ledger.spec.primary_weight
    defensive_deviation = (
        latest.defensive_weight - ledger.spec.defensive_weight
    )
    tolerance = ledger.spec.rebalance_weight_tolerance
    within_tolerance = (
        abs(primary_deviation) <= tolerance
        and abs(defensive_deviation) <= tolerance
        and latest.cash_weight <= tolerance
    )
    drawdown_breached = (
        decision.maximum_drawdown is not None
        and decision.maximum_drawdown < -ledger.spec.maximum_drawdown
    )
    return PaperStatus(
        candidate_id=ledger.spec.candidate_id,
        mode="paper_only_no_broker",
        live_ready=False,
        observation_count=count,
        remaining_validation_observations=max(
            ledger.spec.minimum_forward_observations - count, 0
        ),
        last_observed_on=latest.observed_on,
        portfolio_value=latest.portfolio_value,
        primary_weight=latest.primary_weight,
        defensive_weight=latest.defensive_weight,
        cash_weight=latest.cash_weight,
        primary_weight_deviation=primary_deviation,
        defensive_weight_deviation=defensive_deviation,
        within_rebalance_tolerance=within_tolerance,
        allocation_drift_outside_tolerance=not within_tolerance,
        rebalance_due_next_observation=ledger.spec.is_rebalance_observation(
            count + 1
        ),
        next_rebalance_observation=next_rebalance,
        observations_until_next_rebalance=next_rebalance - count,
        cumulative_return=decision.cumulative_return,
        maximum_drawdown=decision.maximum_drawdown,
        maximum_drawdown_limit=ledger.spec.maximum_drawdown,
        drawdown_limit_breached=drawdown_breached,
        eligible=decision.eligible,
        passed=decision.passed,
        reasons=decision.reasons,
        ledger_hash=ledger.ledger_hash,
    )
