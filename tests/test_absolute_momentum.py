import pandas as pd
import pytest

from project_alpha.absolute_momentum import (
    AbsoluteMomentumConfig,
    run_absolute_momentum,
)


def test_absolute_momentum_is_shifted_unlevered_and_rebalanced_on_schedule():
    prices = pd.Series([100.0 + index for index in range(40)])
    config = AbsoluteMomentumConfig(lookback=5, rebalance_interval=4)

    result = run_absolute_momentum(prices, config)

    assert result["position"].between(0.0, 1.0).all()
    first_positive_signal = result.index[result["momentum"] > 0.0][0]
    assert result.loc[first_positive_signal, "position"] == 0.0
    changed = result["position"].diff().fillna(result["position"]).ne(0.0)
    assert all(index % 4 == 0 for index in result.index[changed])


def test_absolute_momentum_exits_after_negative_signal_at_next_rebalance():
    prices = pd.Series(
        [100.0 + index for index in range(20)]
        + [119.0 - index * 3.0 for index in range(20)]
    )
    config = AbsoluteMomentumConfig(lookback=5, rebalance_interval=3)

    result = run_absolute_momentum(prices, config)

    assert (result["position"].tail(10) == 0.0).any()
    assert (result["cost"] >= 0.0).all()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"lookback": 1},
        {"rebalance_interval": 0},
        {"fee_rate": -0.01},
        {"slippage_rate": -0.01},
    ],
)
def test_absolute_momentum_config_rejects_invalid_values(kwargs):
    with pytest.raises(ValueError):
        AbsoluteMomentumConfig(**kwargs).validate()
