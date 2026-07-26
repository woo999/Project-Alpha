import numpy as np
import pandas as pd

from project_alpha.backtest import BacktestConfig
from project_alpha.data_quality import DataQualityPolicy
from project_alpha.evaluation import AcceptanceCriteria
from project_alpha.pipeline import run_holdout_validation
from project_alpha.stability import StabilityCriteria


def make_prices(rows: int = 400) -> pd.Series:
    returns = np.where(np.arange(rows) % 40 < 30, 0.003, -0.002)
    values = 100.0 * np.cumprod(1.0 + returns)
    return pd.Series(
        values,
        index=pd.date_range("2020-01-01", periods=rows, freq="D"),
    )


def candidates() -> list[BacktestConfig]:
    return [
        BacktestConfig(fast_window=5, slow_window=20),
        BacktestConfig(fast_window=10, slow_window=30),
        BacktestConfig(fast_window=15, slow_window=40),
        BacktestConfig(fast_window=20, slow_window=50),
        BacktestConfig(fast_window=15, slow_window=60),
    ]


def test_pipeline_selects_on_train_and_resets_test_equity():
    result = run_holdout_validation(
        make_prices(),
        candidates(),
        quality_policy=DataQualityPolicy(minimum_rows=200),
    )

    assert result.selected_config in candidates()
    assert len(result.candidate_table) == 5
    assert result.train_end < result.test_start
    first_return = result.test_result["strategy_return"].iloc[0]
    assert result.test_result["equity"].iloc[0] == 1.0 + first_return
    assert set(result.test_metrics) == {"total_return", "max_drawdown", "trades"}


def test_changing_holdout_does_not_change_selected_parameters():
    baseline = make_prices()
    changed_holdout = baseline.copy()
    split_at = int(len(changed_holdout) * 0.70)
    changed_holdout.iloc[split_at:] = (
        changed_holdout.iloc[split_at]
        * np.cumprod(np.full(len(changed_holdout) - split_at, 0.998))
    )
    policy = DataQualityPolicy(minimum_rows=200)

    first = run_holdout_validation(
        baseline,
        candidates(),
        quality_policy=policy,
    )
    second = run_holdout_validation(
        changed_holdout,
        candidates(),
        quality_policy=policy,
    )

    assert first.selected_config == second.selected_config


def test_holdout_receives_explicit_acceptance_decision():
    criteria = AcceptanceCriteria(
        minimum_observations=100,
        minimum_total_return=-1.0,
        minimum_sharpe=-100.0,
        minimum_calmar=-100.0,
        minimum_profit_factor=0.0,
        maximum_drawdown=0.50,
        minimum_trades=0.0,
    )

    result = run_holdout_validation(
        make_prices(),
        candidates(),
        quality_policy=DataQualityPolicy(minimum_rows=200),
        acceptance_criteria=criteria,
        stability_criteria=StabilityCriteria(
            minimum_neighbor_score_ratio=0.0,
            minimum_passing_fraction=0.0,
            maximum_peak_ratio=1_000_000.0,
        ),
    )

    assert result.decision.passed
    assert result.performance_decision.passed
    assert result.stability_report.passed
    assert result.decision.reasons == ()
    assert result.test_performance.observations == 120


def test_default_gate_rejects_holdout_with_too_few_trades():
    result = run_holdout_validation(
        make_prices(),
        candidates(),
        quality_policy=DataQualityPolicy(minimum_rows=200),
    )

    assert not result.decision.passed
    assert any("performance: trades" in reason for reason in result.decision.reasons)
