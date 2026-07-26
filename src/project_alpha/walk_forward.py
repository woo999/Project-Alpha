"""Multi-fold walk-forward validation with aggregate out-of-sample gates."""

from __future__ import annotations

from dataclasses import dataclass, replace

import pandas as pd

from project_alpha.backtest import BacktestConfig
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
from project_alpha.pipeline import HoldoutValidationResult, run_holdout_validation
from project_alpha.stability import StabilityCriteria
from project_alpha.validation import expanding_walk_forward_folds


@dataclass(frozen=True)
class WalkForwardCriteria:
    """Minimum evidence required across independent out-of-sample folds."""

    minimum_folds: int = 3
    minimum_fold_pass_fraction: float = 0.60
    minimum_positive_fold_fraction: float = 0.60

    def validate(self) -> None:
        if self.minimum_folds < 1:
            raise ValueError("minimum_folds must be positive")
        if not 0.0 <= self.minimum_fold_pass_fraction <= 1.0:
            raise ValueError("minimum_fold_pass_fraction must be in [0, 1]")
        if not 0.0 <= self.minimum_positive_fold_fraction <= 1.0:
            raise ValueError("minimum_positive_fold_fraction must be in [0, 1]")


@dataclass(frozen=True)
class WalkForwardValidationResult:
    quality_report: DataQualityReport
    folds: tuple[HoldoutValidationResult, ...]
    aggregate_result: pd.DataFrame
    aggregate_performance: PerformanceMetrics
    aggregate_decision: GateDecision
    fold_pass_fraction: float
    positive_fold_fraction: float
    decision: GateDecision


def _aggregate_out_of_sample(
    folds: list[HoldoutValidationResult],
    *,
    periods_per_year: int,
) -> tuple[pd.DataFrame, PerformanceMetrics]:
    """Join non-overlapping test returns and rebuild one honest equity curve."""
    aggregate = pd.concat([fold.test_result for fold in folds]).sort_index()
    if aggregate.index.has_duplicates:
        raise ValueError("walk-forward test windows overlap")

    aggregate = aggregate.copy()
    aggregate["equity"] = (1.0 + aggregate["strategy_return"]).cumprod()
    aggregate["peak"] = aggregate["equity"].cummax()
    aggregate["drawdown"] = aggregate["equity"] / aggregate["peak"] - 1.0
    metrics = calculate_performance_metrics(
        aggregate,
        periods_per_year=periods_per_year,
    )

    # Each fold's first test position is entered from its own immediately
    # preceding training observation. Summing fold trade counts preserves those
    # boundary transitions instead of inventing transitions between fold models.
    metrics = replace(
        metrics,
        trades=sum(fold.test_performance.trades for fold in folds),
    )
    return aggregate, metrics


def run_walk_forward_validation(
    prices: pd.Series,
    candidates: list[BacktestConfig],
    *,
    min_train: int,
    test_size: int,
    step_size: int | None = None,
    minimum_train_trades: float = 1.0,
    periods_per_year: int = 252,
    quality_policy: DataQualityPolicy | None = None,
    acceptance_criteria: AcceptanceCriteria | None = None,
    stability_criteria: StabilityCriteria | None = None,
    walk_forward_criteria: WalkForwardCriteria | None = None,
) -> WalkForwardValidationResult:
    """Select on expanding history and evaluate only the next unseen segment."""
    rules = walk_forward_criteria or WalkForwardCriteria()
    rules.validate()
    step = test_size if step_size is None else step_size
    if step < test_size:
        raise ValueError(
            "step_size must be at least test_size; overlapping test windows "
            "would double-count out-of-sample observations"
        )

    clean, quality_report = validate_price_series(prices, quality_policy)
    fold_boundaries = expanding_walk_forward_folds(
        len(clean),
        min_train=min_train,
        test_size=test_size,
        step_size=step,
    )

    folds: list[HoldoutValidationResult] = []
    for boundary in fold_boundaries:
        segment = clean.iloc[: boundary.test_end]
        # Pick a ratio in the middle of the integer bin that maps exactly to
        # boundary.train_end when chronological_split applies int().
        train_fraction = (boundary.train_end + 0.5) / boundary.test_end
        result = run_holdout_validation(
            segment,
            candidates,
            train_fraction=train_fraction,
            minimum_test_rows=test_size,
            minimum_train_trades=minimum_train_trades,
            periods_per_year=periods_per_year,
            quality_policy=quality_policy,
            acceptance_criteria=acceptance_criteria,
            stability_criteria=stability_criteria,
        )
        if (
            result.train_end != clean.index[boundary.train_end - 1]
            or result.test_start != clean.index[boundary.test_start]
            or len(result.test_result) != test_size
        ):
            raise RuntimeError("walk-forward fold did not match requested boundaries")
        folds.append(result)

    aggregate_result, aggregate_performance = _aggregate_out_of_sample(
        folds,
        periods_per_year=periods_per_year,
    )
    aggregate_decision = evaluate_acceptance(
        aggregate_performance,
        acceptance_criteria,
    )
    fold_pass_fraction = sum(fold.decision.passed for fold in folds) / len(folds)
    positive_fold_fraction = (
        sum(fold.test_performance.total_return > 0.0 for fold in folds) / len(folds)
    )

    reasons = [
        f"aggregate: {reason}" for reason in aggregate_decision.reasons
    ]
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

    decision = GateDecision(passed=not reasons, reasons=tuple(reasons))
    return WalkForwardValidationResult(
        quality_report=quality_report,
        folds=tuple(folds),
        aggregate_result=aggregate_result,
        aggregate_performance=aggregate_performance,
        aggregate_decision=aggregate_decision,
        fold_pass_fraction=fold_pass_fraction,
        positive_fold_fraction=positive_fold_fraction,
        decision=decision,
    )
