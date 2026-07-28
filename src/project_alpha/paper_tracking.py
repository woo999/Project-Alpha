"""Immutable paper-tracking records for predeclared research candidates.

This module does not connect to a broker or place orders.  It only prevents a
historical candidate from being silently changed after forward observations
begin.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
import hashlib
import json
import math
from typing import Iterable


@dataclass(frozen=True)
class CandidateSpec:
    candidate_id: str
    declared_on: date
    historical_cutoff: date
    primary_symbol: str
    defensive_symbol: str
    primary_weight: float
    defensive_weight: float
    rebalance_interval_trading_days: int
    rebalance_anchor: str = "first_forward_observation"
    rebalance_weight_tolerance: float = 0.01
    minimum_transaction_cost_rate: float = 0.004
    maximum_drawdown: float = 0.20
    minimum_forward_observations: int = 252

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id cannot be empty")
        if self.declared_on <= self.historical_cutoff:
            raise ValueError("declared_on must be after historical_cutoff")
        if not math.isclose(
            self.primary_weight + self.defensive_weight, 1.0, abs_tol=1e-12
        ):
            raise ValueError("candidate weights must sum to 1")
        if min(self.primary_weight, self.defensive_weight) < 0:
            raise ValueError("candidate weights cannot be negative")
        if self.rebalance_interval_trading_days < 1:
            raise ValueError("rebalance interval must be positive")
        if self.rebalance_anchor != "first_forward_observation":
            raise ValueError(
                "rebalance_anchor must be 'first_forward_observation'"
            )
        if not 0 < self.rebalance_weight_tolerance < 0.10:
            raise ValueError("rebalance_weight_tolerance must be in (0, 0.10)")
        if not 0 <= self.minimum_transaction_cost_rate < 0.10:
            raise ValueError("minimum_transaction_cost_rate must be in [0, 0.10)")
        if not 0 < self.maximum_drawdown < 1:
            raise ValueError("maximum_drawdown must be between 0 and 1")
        if self.minimum_forward_observations < 2:
            raise ValueError("minimum_forward_observations must be at least 2")

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            asdict(self), sort_keys=True, default=str, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def is_rebalance_observation(self, observation_number: int) -> bool:
        """Return whether this 1-based forward observation is a rebalance date.

        Observation 1 establishes the frozen target allocation.  Subsequent
        rebalances occur after each complete interval: 64, 127, ... for a
        63-trading-day interval.
        """
        if observation_number < 1:
            raise ValueError("observation_number must be positive")
        return (
            observation_number - 1
        ) % self.rebalance_interval_trading_days == 0


@dataclass(frozen=True)
class PaperObservation:
    observed_on: date
    portfolio_value: float
    primary_close: float
    defensive_close: float
    primary_units: int
    defensive_units: int
    cash_balance: float
    turnover_today: float = 0.0
    charged_transaction_costs_today: float = 0.0

    def __post_init__(self) -> None:
        values = (
            self.portfolio_value,
            self.primary_close,
            self.defensive_close,
        )
        if any(not math.isfinite(value) or value <= 0 for value in values):
            raise ValueError("paper observation values must be finite and positive")
        units = (self.primary_units, self.defensive_units)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in units):
            raise ValueError("paper position units must be integers")
        if any(value < 0 for value in units):
            raise ValueError("paper position units cannot be negative")
        if not math.isfinite(self.cash_balance) or self.cash_balance < 0:
            raise ValueError("cash_balance must be finite and non-negative")
        trading_values = (
            self.turnover_today,
            self.charged_transaction_costs_today,
        )
        if any(not math.isfinite(value) or value < 0 for value in trading_values):
            raise ValueError("turnover and transaction costs must be non-negative")
        if self.turnover_today == 0 and self.charged_transaction_costs_today != 0:
            raise ValueError("transaction costs require positive turnover")
        reconstructed = (
            self.primary_units * self.primary_close
            + self.defensive_units * self.defensive_close
            + self.cash_balance
        )
        if not math.isclose(
            self.portfolio_value, reconstructed, rel_tol=1e-9, abs_tol=0.01
        ):
            raise ValueError(
                "portfolio_value must equal marked positions plus cash_balance"
            )

    @property
    def primary_weight(self) -> float:
        return self.primary_units * self.primary_close / self.portfolio_value

    @property
    def defensive_weight(self) -> float:
        return self.defensive_units * self.defensive_close / self.portfolio_value

    @property
    def cash_weight(self) -> float:
        return self.cash_balance / self.portfolio_value


@dataclass(frozen=True)
class PaperDecision:
    passed: bool
    eligible: bool
    observation_count: int
    cumulative_return: float | None
    maximum_drawdown: float | None
    reasons: tuple[str, ...]


@dataclass
class PaperLedger:
    spec: CandidateSpec
    observations: list[PaperObservation] = field(default_factory=list)

    def append(self, observation: PaperObservation) -> None:
        if observation.observed_on <= self.spec.historical_cutoff:
            raise ValueError("paper observations must be after historical cutoff")
        if self.observations and observation.observed_on <= self.observations[-1].observed_on:
            raise ValueError("paper observations must be strictly chronological")
        observation_number = len(self.observations) + 1
        is_rebalance = self.spec.is_rebalance_observation(observation_number)
        if not is_rebalance and observation.turnover_today != 0:
            raise ValueError("turnover is forbidden outside rebalance observations")
        if observation_number == 1 and observation.turnover_today <= 0:
            raise ValueError("initial allocation must record positive turnover")
        if observation.turnover_today > 0:
            minimum_cost = (
                observation.turnover_today
                * self.spec.minimum_transaction_cost_rate
            )
            if observation.charged_transaction_costs_today + 1e-12 < minimum_cost:
                raise ValueError(
                    "charged transaction costs are below the frozen minimum rate"
                )
        if is_rebalance:
            tolerance = self.spec.rebalance_weight_tolerance
            if (
                abs(observation.primary_weight - self.spec.primary_weight) > tolerance
                or abs(observation.defensive_weight - self.spec.defensive_weight)
                > tolerance
                or observation.cash_weight > tolerance
            ):
                raise ValueError(
                    "rebalance observation does not match frozen target weights"
                )
        self.observations.append(observation)

    def extend(self, observations: Iterable[PaperObservation]) -> None:
        for observation in observations:
            self.append(observation)

    def evaluate(self) -> PaperDecision:
        count = len(self.observations)
        if count < 2:
            return PaperDecision(
                passed=False,
                eligible=False,
                observation_count=count,
                cumulative_return=None,
                maximum_drawdown=None,
                reasons=("insufficient forward observations",),
            )

        values = [item.portfolio_value for item in self.observations]
        cumulative_return = values[-1] / values[0] - 1
        peak = values[0]
        maximum_drawdown = 0.0
        for value in values:
            peak = max(peak, value)
            maximum_drawdown = min(maximum_drawdown, value / peak - 1)

        reasons: list[str] = []
        if count < self.spec.minimum_forward_observations:
            reasons.append(
                f"requires {self.spec.minimum_forward_observations} forward observations"
            )
        if cumulative_return <= 0:
            reasons.append("forward cumulative return is not positive")
        if maximum_drawdown < -self.spec.maximum_drawdown:
            reasons.append("forward maximum drawdown exceeds the frozen limit")

        eligible = count >= self.spec.minimum_forward_observations
        return PaperDecision(
            passed=eligible and not reasons,
            eligible=eligible,
            observation_count=count,
            cumulative_return=cumulative_return,
            maximum_drawdown=maximum_drawdown,
            reasons=tuple(reasons),
        )
