import pandas as pd
import pytest

from project_alpha.core_protection import (
    CoreProtectionConfig,
    run_core_protection,
)


def test_core_protection_keeps_core_and_is_shifted_and_unlevered():
    prices = pd.Series([100.0 + index for index in range(50)])
    config = CoreProtectionConfig(
        trend_window=10,
        core_weight=0.70,
        rebalance_interval=5,
    )

    result = run_core_protection(prices, config)

    assert result["position"].between(0.70, 1.0).all()
    first_trend_day = result.index[result["close"] > result["trend_average"]][0]
    assert result.loc[first_trend_day, "position"] == 0.70
    changed = result["position"].diff().fillna(0.0).ne(0.0)
    assert all(index % 5 == 0 for index in result.index[changed])


def test_core_protection_never_goes_to_cash_in_decline():
    prices = pd.Series([150.0 - index for index in range(50)])
    config = CoreProtectionConfig(
        trend_window=10,
        core_weight=0.70,
        rebalance_interval=5,
    )

    result = run_core_protection(prices, config)

    assert (result["position"] == 0.70).all()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"trend_window": 1},
        {"core_weight": -0.01},
        {"core_weight": 1.01},
        {"rebalance_interval": 0},
    ],
)
def test_core_protection_rejects_invalid_values(kwargs):
    with pytest.raises(ValueError):
        CoreProtectionConfig(**kwargs).validate()
