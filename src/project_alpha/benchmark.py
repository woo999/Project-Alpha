"""Benchmark diagnostics that separate strategy behavior from market beta."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from project_alpha.evaluation import (
    PerformanceMetrics,
    calculate_performance_metrics,
)


@dataclass(frozen=True)
class BenchmarkReport:
    """Out-of-sample strategy comparison with frictionless buy-and-hold."""

    benchmark_name: str
    benchmark_performance: PerformanceMetrics
    excess_total_return: float
    drawdown_improvement: float
    sharpe_improvement: float
    calmar_improvement: float


def _difference(strategy_value: float, benchmark_value: float) -> float:
    """Subtract ratios without producing NaN for equal infinities."""
    if math.isinf(strategy_value) and math.isinf(benchmark_value):
        if strategy_value == benchmark_value:
            return 0.0
    return strategy_value - benchmark_value


def compare_buy_and_hold(
    result: pd.DataFrame,
    strategy_performance: PerformanceMetrics,
    *,
    periods_per_year: int = 252,
) -> BenchmarkReport:
    """Compare cost-adjusted strategy returns with the underlying asset."""
    if "asset_return" not in result.columns:
        raise ValueError("result is missing columns: ['asset_return']")
    if result.empty:
        raise ValueError("result cannot be empty")

    benchmark = pd.DataFrame(index=result.index)
    benchmark["strategy_return"] = pd.to_numeric(
        result["asset_return"],
        errors="raise",
    ).astype(float)
    benchmark["position"] = 1.0
    benchmark["equity"] = (1.0 + benchmark["strategy_return"]).cumprod()
    benchmark["peak"] = benchmark["equity"].cummax()
    benchmark["drawdown"] = benchmark["equity"] / benchmark["peak"] - 1.0
    benchmark_performance = calculate_performance_metrics(
        benchmark,
        periods_per_year=periods_per_year,
    )

    return BenchmarkReport(
        benchmark_name="frictionless_buy_and_hold",
        benchmark_performance=benchmark_performance,
        excess_total_return=(
            strategy_performance.total_return
            - benchmark_performance.total_return
        ),
        drawdown_improvement=(
            strategy_performance.max_drawdown
            - benchmark_performance.max_drawdown
        ),
        sharpe_improvement=_difference(
            strategy_performance.sharpe,
            benchmark_performance.sharpe,
        ),
        calmar_improvement=_difference(
            strategy_performance.calmar,
            benchmark_performance.calmar,
        ),
    )
