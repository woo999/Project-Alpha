import numpy as np
import pandas as pd
import pytest

from project_alpha.backtest import BacktestConfig
from project_alpha.data_quality import DataQualityPolicy
from project_alpha.evaluation import AcceptanceCriteria
from project_alpha.stability import StabilityCriteria
from project_alpha.walk_forward import (
    WalkForwardCriteria,
    run_walk_forward_validation,
)


def make_prices(rows: int = 600) -> pd.Series:
    returns = np.where(np.arange(rows) % 40 < 30, 0.003, -0.002)
    return pd.Series(
        100.0 * np.cumprod(1.0 + returns),
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


def loose_acceptance() -> AcceptanceCriteria:
    return AcceptanceCriteria(
        minimum_observations=90,
        minimum_total_return=-1.0,
        minimum_sharpe=-100.0,
        minimum_calmar=-100.0,
        minimum_profit_factor=0.0,
        maximum_drawdown=0.50,
        minimum_trades=0.0,
    )


def loose_stability() -> StabilityCriteria:
    return StabilityCriteria(
        minimum_neighbor_score_ratio=0.0,
        minimum_passing_fraction=0.0,
        maximum_peak_ratio=1_000_000.0,
    )


def test_walk_forward_builds_unique_aggregate_out_of_sample_curve():
    result = run_walk_forward_validation(
        make_prices(),
        candidates(),
        min_train=200,
        test_size=100,
        quality_policy=DataQualityPolicy(minimum_rows=200),
        acceptance_criteria=loose_acceptance(),
        stability_criteria=loose_stability(),
        walk_forward_criteria=WalkForwardCriteria(
            minimum_folds=4,
            minimum_fold_pass_fraction=0.0,
            minimum_positive_fold_fraction=0.0,
        ),
    )

    assert len(result.folds) == 4
    assert len(result.aggregate_result) == 400
    assert result.aggregate_result.index.is_unique
    assert result.aggregate_performance.observations == 400
    assert result.benchmark_report.benchmark_performance.observations == 400
    assert result.benchmark_report.benchmark_name == "frictionless_buy_and_hold"
    assert result.aggregate_decision.passed
    assert result.decision.passed
    for previous, current in zip(result.folds, result.folds[1:]):
        assert previous.test_result.index[-1] < current.test_result.index[0]


def test_walk_forward_rejects_overlapping_test_windows():
    with pytest.raises(ValueError, match="overlapping test windows"):
        run_walk_forward_validation(
            make_prices(),
            candidates(),
            min_train=200,
            test_size=100,
            step_size=50,
            quality_policy=DataQualityPolicy(minimum_rows=200),
        )


def test_walk_forward_default_rules_fail_closed():
    result = run_walk_forward_validation(
        make_prices(),
        candidates(),
        min_train=200,
        test_size=100,
        quality_policy=DataQualityPolicy(minimum_rows=200),
    )

    assert not result.decision.passed
    assert result.decision.reasons
