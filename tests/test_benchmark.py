import pandas as pd

from project_alpha.benchmark import (
    BenchmarkCriteria,
    compare_buy_and_hold,
    evaluate_benchmark_acceptance,
)
from project_alpha.evaluation import calculate_performance_metrics


def make_result(asset_returns, strategy_returns, positions):
    result = pd.DataFrame(
        {
            "asset_return": asset_returns,
            "strategy_return": strategy_returns,
            "position": positions,
        }
    )
    result["equity"] = (1.0 + result["strategy_return"]).cumprod()
    result["peak"] = result["equity"].cummax()
    result["drawdown"] = result["equity"] / result["peak"] - 1.0
    return result


def test_buy_and_hold_matches_an_always_invested_costless_strategy():
    result = make_result(
        [0.0, 0.02, -0.01, 0.03],
        [0.0, 0.02, -0.01, 0.03],
        [1.0, 1.0, 1.0, 1.0],
    )
    strategy = calculate_performance_metrics(result)

    report = compare_buy_and_hold(result, strategy)

    assert abs(report.excess_total_return) < 1e-12
    assert abs(report.drawdown_improvement) < 1e-12
    assert abs(report.sharpe_improvement) < 1e-12
    assert abs(report.calmar_improvement) < 1e-12


def test_cash_filter_can_show_drawdown_improvement_separately_from_return():
    result = make_result(
        [0.0, 0.10, -0.30, 0.05],
        [0.0, 0.10, 0.0, 0.0],
        [1.0, 1.0, 0.0, 0.0],
    )
    strategy = calculate_performance_metrics(result)

    report = compare_buy_and_hold(result, strategy)

    assert report.drawdown_improvement > 0.0
    assert (
        report.excess_total_return
        == strategy.total_return - report.benchmark_performance.total_return
    )


def test_benchmark_gate_rejects_lagging_strategy_without_risk_improvement():
    result = make_result(
        [0.0, 0.10, -0.05, 0.10],
        [0.0, 0.02, -0.05, 0.02],
        [1.0, 1.0, 1.0, 1.0],
    )
    report = compare_buy_and_hold(
        result,
        calculate_performance_metrics(result),
    )

    decision = evaluate_benchmark_acceptance(report)

    assert not decision.passed
    assert "neither beat buy-and-hold" in decision.reasons[0]


def test_benchmark_gate_accepts_material_risk_adjusted_improvement():
    result = make_result(
        [0.0, 0.10, -0.30, 0.05],
        [0.0, 0.08, 0.0, 0.0],
        [1.0, 1.0, 0.0, 0.0],
    )
    report = compare_buy_and_hold(
        result,
        calculate_performance_metrics(result),
    )

    decision = evaluate_benchmark_acceptance(
        report,
        BenchmarkCriteria(minimum_drawdown_improvement=0.05),
    )

    assert decision.passed
