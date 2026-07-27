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


@dataclass(frozen=True)
class PaperObservation:
    observed_on: date
    portfolio_value: float
    primary_close: float
    defensive_close: float

    def __post_init__(self) -> None:
        values = (
            self.portfolio_value,
            self.primary_close,
            self.defensive_close,
        )
        if any(not math.isfinite(value) or value <= 0 for value in values):
            raise ValueError("paper observation values must be finite and positive")


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
