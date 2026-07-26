"""Transaction-cost stress tests for out-of-sample backtest results."""

from __future__ import annotations

from dataclasses import dataclass, replace

import pandas as pd

from project_alpha.evaluation import (
    AcceptanceCriteria,
    GateDecision,
    PerformanceMetrics,
    calculate_performance_metrics,
    evaluate_acceptance,
)


@dataclass(frozen=True)
class CostStressCriteria:
    """Cost multipliers that every promoted strategy should survive."""

    multipliers: tuple[float, ...] = (1.0, 1.5, 2.0)
    minimum_pass_fraction: float = 1.0

    def validate(self) -> None:
        if len(self.multipliers) < 2:
            raise ValueError("at least two cost multipliers are required")
        if self.multipliers[0] != 1.0:
            raise ValueError("cost multipliers must begin with the 1.0 baseline")
        if any(multiplier < 1.0 for multiplier in self.multipliers):
            raise ValueError("cost multipliers cannot reduce assumed costs")
        if any(
            current <= previous
            for previous, current in zip(
                self.multipliers,
                self.multipliers[1:],
            )
        ):
            raise ValueError("cost multipliers must be strictly increasing")
        if not 0.0 <= self.minimum_pass_fraction <= 1.0:
            raise ValueError("minimum_pass_fraction must be in [0, 1]")


@dataclass(frozen=True)
class CostStressScenario:
    multiplier: float
    performance: PerformanceMetrics
    decision: GateDecision


@dataclass(frozen=True)
class CostStressReport:
    scenarios: tuple[CostStressScenario, ...]
    pass_fraction: float
    decision: GateDecision


def evaluate_cost_stress(
    result: pd.DataFrame,
    *,
    periods_per_year: int = 252,
    acceptance_criteria: AcceptanceCriteria | None = None,
    stress_criteria: CostStressCriteria | None = None,
    trade_count: float | None = None,
) -> CostStressReport:
    """Reprice the same out-of-sample trades under worse execution costs."""
    rules = stress_criteria or CostStressCriteria()
    rules.validate()
    required = {"position", "asset_return", "turnover", "cost"}
    missing = required.difference(result.columns)
    if missing:
        raise ValueError(f"result is missing columns: {sorted(missing)}")
    if trade_count is not None and trade_count < 0.0:
        raise ValueError("trade_count cannot be negative")

    scenarios: list[CostStressScenario] = []
    for multiplier in rules.multipliers:
        stressed = result.copy()
        stressed["cost"] = stressed["cost"] * multiplier
        stressed["strategy_return"] = (
            stressed["position"] * stressed["asset_return"] - stressed["cost"]
        )
        stressed["equity"] = (1.0 + stressed["strategy_return"]).cumprod()
        stressed["peak"] = stressed["equity"].cummax()
        stressed["drawdown"] = stressed["equity"] / stressed["peak"] - 1.0
        performance = calculate_performance_metrics(
            stressed,
            periods_per_year=periods_per_year,
        )
        if trade_count is not None:
            performance = replace(performance, trades=trade_count)
        decision = evaluate_acceptance(performance, acceptance_criteria)
        scenarios.append(
            CostStressScenario(
                multiplier=multiplier,
                performance=performance,
                decision=decision,
            )
        )

    pass_fraction = sum(item.decision.passed for item in scenarios) / len(scenarios)
    reasons: list[str] = []
    for scenario in scenarios:
        reasons.extend(
            f"{scenario.multiplier:.1f}x costs: {reason}"
            for reason in scenario.decision.reasons
        )
    if pass_fraction < rules.minimum_pass_fraction:
        reasons.append(
            f"cost_stress_pass_fraction {pass_fraction:.2f} < "
            f"{rules.minimum_pass_fraction:.2f}"
        )
    return CostStressReport(
        scenarios=tuple(scenarios),
        pass_fraction=pass_fraction,
        decision=GateDecision(passed=not reasons, reasons=tuple(reasons)),
    )
