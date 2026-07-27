import numpy as np
import pandas as pd
import pytest

from project_alpha.backtest import BacktestConfig
from project_alpha.data_quality import DataQualityPolicy
from project_alpha.evaluation import AcceptanceCriteria
from project_alpha.fixed_validation import run_fixed_sma_walk_forward
from project_alpha.walk_forward import WalkForwardCriteria


def make_prices(rows: int = 600) -> pd.Series:
    returns = np.where(np.arange(rows) % 40 < 30, 0.003, -0.002)
    return pd.Series(
        100.0 * np.cumprod(1.0 + returns),
        index=pd.date_range("2020-01-01", periods=rows, freq="D"),
    )


def test_fixed_rule_is_unchanged_across_unique_test_folds():
    loose = AcceptanceCriteria(
        minimum_observations=90,
        minimum_total_return=-1.0,
        minimum_sharpe=-100.0,
        minimum_calmar=-100.0,
        minimum_profit_factor=0.0,
        maximum_drawdown=0.50,
        minimum_trades=0.0,
    )
    config = BacktestConfig(20, 100)
    result = run_fixed_sma_walk_forward(
        make_prices(),
        config,
        min_train=200,
        test_size=100,
        quality_policy=DataQualityPolicy(minimum_rows=200),
        acceptance_criteria=loose,
        walk_forward_criteria=WalkForwardCriteria(
            minimum_folds=4,
            minimum_fold_pass_fraction=0.0,
            minimum_positive_fold_fraction=0.0,
        ),
    )

    assert result.config == config
    assert len(result.folds) == 4
    assert len(result.aggregate_result) == 400
    assert result.aggregate_result.index.is_unique
    assert result.decision.passed


def test_fixed_rule_rejects_overlapping_test_windows():
    with pytest.raises(ValueError, match="overlapping"):
        run_fixed_sma_walk_forward(
            make_prices(),
            BacktestConfig(20, 100),
            min_train=200,
            test_size=100,
            step_size=50,
            quality_policy=DataQualityPolicy(minimum_rows=200),
        )
