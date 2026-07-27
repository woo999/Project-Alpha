"""Walk-forward validation for a fixed, predeclared SMA configuration."""

from __future__ import annotations

from dataclasses import dataclass, replace

import pandas as pd

from project_alpha.backtest import BacktestConfig, run_long_only_sma
from project_alpha.benchmark import BenchmarkReport, compare_buy_and_hold
from project_alpha.cost_stress import (
    CostStressCriteria,
    CostStressReport,
    evaluate_cost_stress,
)
from project_alpha.data_quality import (
    DataQualityPolicy,
    DataQualityReport,
    validate_price_series,
)
from project_alpha.evaluation import (
    AcceptanceCriteria,
    GateDecision,
    PerformanceMetrics,
    calculate_performance_metrics,
    evaluate_acceptance,
)
from project_alpha.validation import expanding_walk_forward_folds
from project_alpha.walk_forward import WalkForwardCriteria


@dataclass(frozen=True)
class FixedFoldResult:
    train_end: object
    test_start: object
    test_result: pd.DataFrame
    performance: PerformanceMetrics
    decision: GateDecision


@dataclass(frozen=True)
class FixedWalkForwardResult:
    config: BacktestConfig
    quality_report: DataQualityReport
    folds: tuple[FixedFoldResult, ...]
    aggregate_result: pd.DataFrame
    aggregate_performance: PerformanceMetrics
    aggregate_decision: GateDecision
    benchmark_report: BenchmarkReport
    cost_stress_report: CostStressReport
    fold_pass_fraction: float
    positive_fold_fraction: float
    decision: GateDecision


def _reset_equity(result: pd.DataFrame) -> pd.DataFrame:
    reset = result.copy()
    reset["equity"] = (1.0 + reset["strategy_return"]).cumprod()
    reset["peak"] = reset["equity"].cummax()
    reset["drawdown"] = reset["equity"] / reset["peak"] - 1.0
    return reset


def run_fixed_sma_walk_forward(
    prices: pd.Series,
    config: BacktestConfig,
    *,
    min_train: int,
    test_size: int,
    step_size: int | None = None,
    periods_per_year: int = 252,
    quality_policy: DataQualityPolicy | None = None,
    acceptance_criteria: AcceptanceCriteria | None = None,
    walk_forward_criteria: WalkForwardCriteria | None = None,
    cost_stress_criteria: CostStressCriteria | None = None,
) -> FixedWalkForwardResult:
    """Evaluate one unchanged rule over successive unseen periods."""
    config.validate()
    if min_train <= config.slow_window:
        raise ValueError("min_train must exceed the slow window")
    rules = walk_forward_criteria or WalkForwardCriteria()
    rules.validate()
    step = test_size if step_size is None else step_size
    if step < test_size:
        raise ValueError("overlapping test windows are not allowed")

    clean, quality_report = validate_price_series(prices, quality_policy)
    boundaries = expanding_walk_forward_folds(
        len(clean),
        min_train=min_train,
        test_size=test_size,
        step_size=step,
    )

    folds: list[FixedFoldResult] = []
    for boundary in boundaries:
        segment = clean.iloc[: boundary.test_end]
        full_result = run_long_only_sma(segment, config)
        test_result = _reset_equity(
            full_result.iloc[boundary.test_start : boundary.test_end]
        )
        performance = calculate_performance_metrics(
            test_result,
            periods_per_year=periods_per_year,
        )
        decision = evaluate_acceptance(performance, acceptance_criteria)
        folds.append(
            FixedFoldResult(
                train_end=clean.index[boundary.train_end - 1],
                test_start=clean.index[boundary.test_start],
                test_result=test_result,
                performance=performance,
                decision=decision,
            )
        )

    aggregate = pd.concat([fold.test_result for fold in folds]).sort_index()
    if aggregate.index.has_duplicates:
        raise ValueError("walk-forward test windows overlap")
    aggregate = _reset_equity(aggregate)
    aggregate_performance = calculate_performance_metrics(
        aggregate,
        periods_per_year=periods_per_year,
    )
    aggregate_performance = replace(
        aggregate_performance,
        trades=sum(fold.performance.trades for fold in folds),
    )
    aggregate_decision = evaluate_acceptance(
        aggregate_performance,
        acceptance_criteria,
    )
    benchmark_report = compare_buy_and_hold(
        aggregate,
        aggregate_performance,
        periods_per_year=periods_per_year,
    )
    cost_stress_report = evaluate_cost_stress(
        aggregate,
        periods_per_year=periods_per_year,
        acceptance_criteria=acceptance_criteria,
        stress_criteria=cost_stress_criteria,
        trade_count=aggregate_performance.trades,
    )
    fold_pass_fraction = sum(fold.decision.passed for fold in folds) / len(folds)
    positive_fold_fraction = (
        sum(fold.performance.total_return > 0.0 for fold in folds) / len(folds)
    )

    reasons = [f"aggregate: {reason}" for reason in aggregate_decision.reasons]
    reasons.extend(
        f"cost_stress: {reason}"
        for reason in cost_stress_report.decision.reasons
    )
    if len(folds) < rules.minimum_folds:
        reasons.append(f"fold_count {len(folds)} < {rules.minimum_folds}")
    if fold_pass_fraction < rules.minimum_fold_pass_fraction:
        reasons.append(
            f"fold_pass_fraction {fold_pass_fraction:.2f} < "
            f"{rules.minimum_fold_pass_fraction:.2f}"
        )
    if positive_fold_fraction < rules.minimum_positive_fold_fraction:
        reasons.append(
            f"positive_fold_fraction {positive_fold_fraction:.2f} < "
            f"{rules.minimum_positive_fold_fraction:.2f}"
        )

    return FixedWalkForwardResult(
        config=config,
        quality_report=quality_report,
        folds=tuple(folds),
        aggregate_result=aggregate,
        aggregate_performance=aggregate_performance,
        aggregate_decision=aggregate_decision,
        benchmark_report=benchmark_report,
        cost_stress_report=cost_stress_report,
        fold_pass_fraction=fold_pass_fraction,
        positive_fold_fraction=positive_fold_fraction,
        decision=GateDecision(passed=not reasons, reasons=tuple(reasons)),
    )
