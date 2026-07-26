"""End-to-end holdout validation with explicit anti-leakage boundaries."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from project_alpha.backtest import BacktestConfig, run_long_only_sma, summarize
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
from project_alpha.stability import (
    StabilityCriteria,
    StabilityReport,
    analyze_parameter_stability,
)
from project_alpha.validation import chronological_split


@dataclass(frozen=True)
class HoldoutValidationResult:
    selected_config: BacktestConfig
    quality_report: DataQualityReport
    train_metrics: dict[str, float]
    test_metrics: dict[str, float]
    test_performance: PerformanceMetrics
    performance_decision: GateDecision
    stability_report: StabilityReport
    decision: GateDecision
    candidate_table: pd.DataFrame
    train_end: object
    test_start: object
    test_result: pd.DataFrame


def _selection_score(metrics: dict[str, float]) -> float:
    """Prefer return per unit of drawdown, with a small stability floor."""
    drawdown_risk = max(abs(metrics["max_drawdown"]), 0.01)
    return metrics["total_return"] / drawdown_risk


def _reset_equity(result: pd.DataFrame) -> pd.DataFrame:
    """Make a period's equity and drawdown independent of prior history."""
    reset = result.copy()
    reset["equity"] = (1.0 + reset["strategy_return"]).cumprod()
    reset["peak"] = reset["equity"].cummax()
    reset["drawdown"] = reset["equity"] / reset["peak"] - 1.0
    return reset


def run_holdout_validation(
    prices: pd.Series,
    candidates: list[BacktestConfig],
    *,
    train_fraction: float = 0.70,
    minimum_test_rows: int = 30,
    minimum_train_trades: float = 1.0,
    periods_per_year: int = 252,
    quality_policy: DataQualityPolicy | None = None,
    acceptance_criteria: AcceptanceCriteria | None = None,
    stability_criteria: StabilityCriteria | None = None,
) -> HoldoutValidationResult:
    """Select parameters on training data and evaluate once on holdout data."""
    if not candidates:
        raise ValueError("at least one candidate configuration is required")
    if minimum_train_trades < 0:
        raise ValueError("minimum_train_trades cannot be negative")
    for candidate in candidates:
        candidate.validate()

    clean, quality_report = validate_price_series(prices, quality_policy)
    minimum_train_rows = max(candidate.slow_window for candidate in candidates) + 2
    train, test = chronological_split(
        clean,
        train_fraction,
        min_train=minimum_train_rows,
        min_test=minimum_test_rows,
    )

    records: list[dict[str, float | int]] = []
    eligible: list[tuple[float, int, BacktestConfig, dict[str, float]]] = []
    for index, candidate in enumerate(candidates):
        train_result = run_long_only_sma(train, candidate)
        metrics = summarize(train_result)
        score = _selection_score(metrics)
        records.append(
            {
                "candidate_index": index,
                "fast_window": candidate.fast_window,
                "slow_window": candidate.slow_window,
                "fee_rate": candidate.fee_rate,
                "slippage_rate": candidate.slippage_rate,
                **metrics,
                "selection_score": score,
            }
        )
        if metrics["trades"] >= minimum_train_trades:
            eligible.append((score, -index, candidate, metrics))

    if not eligible:
        raise ValueError("no candidate met the minimum training trade count")

    _, negative_index, selected_config, train_metrics = max(
        eligible, key=lambda item: item[:2]
    )
    selected_candidate_index = -negative_index
    candidate_table = pd.DataFrame.from_records(records)
    stability_report = analyze_parameter_stability(
        candidate_table,
        selected_candidate_index,
        stability_criteria,
    )

    # Calculate indicators using prior training history, then expose only the
    # untouched holdout rows and reset its equity curve to 1.0.
    full_result = run_long_only_sma(clean, selected_config)
    test_result = _reset_equity(full_result.loc[test.index])
    test_metrics = summarize(test_result)
    test_performance = calculate_performance_metrics(
        test_result,
        periods_per_year=periods_per_year,
    )
    performance_decision = evaluate_acceptance(
        test_performance, acceptance_criteria
    )
    combined_reasons = tuple(
        [f"performance: {reason}" for reason in performance_decision.reasons]
        + [f"stability: {reason}" for reason in stability_report.reasons]
    )
    decision = GateDecision(
        passed=performance_decision.passed and stability_report.passed,
        reasons=combined_reasons,
    )

    return HoldoutValidationResult(
        selected_config=selected_config,
        quality_report=quality_report,
        train_metrics=train_metrics,
        test_metrics=test_metrics,
        test_performance=test_performance,
        performance_decision=performance_decision,
        stability_report=stability_report,
        decision=decision,
        candidate_table=candidate_table,
        train_end=train.index[-1],
        test_start=test.index[0],
        test_result=test_result,
    )
