import numpy as np
import pandas as pd

from project_alpha.evaluation import (
    AcceptanceCriteria,
    calculate_performance_metrics,
    evaluate_acceptance,
)


def make_result(returns: np.ndarray, position: np.ndarray) -> pd.DataFrame:
    equity = pd.Series(1.0 + returns).cumprod()
    peak = equity.cummax()
    return pd.DataFrame(
        {
            "strategy_return": returns,
            "equity": equity,
            "drawdown": equity / peak - 1.0,
            "position": position,
        }
    )


def test_metrics_capture_risk_cost_adjusted_returns_and_activity():
    returns = np.tile(np.array([0.01, 0.004, -0.003, 0.002]), 30)
    position = np.tile(np.array([0.0, 1.0, 1.0, 0.0]), 30)

    metrics = calculate_performance_metrics(make_result(returns, position))

    assert metrics.observations == 120
    assert metrics.total_return > 0.0
    assert metrics.annualized_volatility > 0.0
    assert metrics.max_drawdown < 0.0
    assert metrics.profit_factor > 1.0
    assert 0.0 < metrics.exposure < 1.0
    assert metrics.trades > 5.0


def test_gate_passes_only_when_every_rule_passes():
    returns = np.tile(np.array([0.01, 0.004, -0.003, 0.002]), 30)
    position = np.tile(np.array([0.0, 1.0, 1.0, 0.0]), 30)
    metrics = calculate_performance_metrics(make_result(returns, position))
    criteria = AcceptanceCriteria(
        minimum_observations=100,
        minimum_sharpe=0.1,
        minimum_calmar=0.1,
        minimum_profit_factor=1.01,
        maximum_drawdown=0.20,
        minimum_trades=5.0,
    )

    decision = evaluate_acceptance(metrics, criteria)

    assert decision.passed
    assert decision.reasons == ()


def test_gate_lists_all_rejection_reasons():
    returns = np.full(40, -0.01)
    position = np.ones(40)
    metrics = calculate_performance_metrics(make_result(returns, position))

    decision = evaluate_acceptance(metrics)

    assert not decision.passed
    assert len(decision.reasons) >= 4
    assert any("observations" in reason for reason in decision.reasons)
    assert any("total_return" in reason for reason in decision.reasons)
    assert any("trades" in reason for reason in decision.reasons)
