import pandas as pd
import pytest

from project_alpha.risk_managed import (
    VolatilityManagedTrendConfig,
    run_volatility_managed_trend,
)


def test_volatility_managed_strategy_is_unlevered_and_shifted():
    prices = pd.Series(
        [100.0 + index * 0.2 + (index % 3) * 0.1 for index in range(80)]
    )
    config = VolatilityManagedTrendConfig(
        trend_window=20,
        volatility_window=10,
        target_annualized_volatility=0.10,
    )

    result = run_volatility_managed_trend(prices, config)

    assert result["position"].between(0.0, 1.0).all()
    first_trend_day = result.index[result["close"] > result["trend_average"]][0]
    assert result.loc[first_trend_day, "position"] == 0.0
    assert (result["cost"] >= 0.0).all()


def test_maximum_exposure_cannot_enable_leverage():
    with pytest.raises(ValueError, match="maximum_exposure"):
        VolatilityManagedTrendConfig(maximum_exposure=1.1).validate()


def test_scheduled_buffered_rebalancing_reduces_turnover():
    prices = pd.Series(
        [100.0 + index * 0.15 + (index % 7) * 0.8 for index in range(180)]
    )
    daily = run_volatility_managed_trend(
        prices,
        VolatilityManagedTrendConfig(
            trend_window=30,
            volatility_window=10,
            target_annualized_volatility=0.125,
        ),
    )
    buffered = run_volatility_managed_trend(
        prices,
        VolatilityManagedTrendConfig(
            trend_window=30,
            volatility_window=10,
            target_annualized_volatility=0.125,
            rebalance_interval=5,
            minimum_weight_change=0.05,
        ),
    )

    assert buffered["turnover"].sum() <= daily["turnover"].sum()
    assert buffered["position"].between(0.0, 1.0).all()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"rebalance_interval": 0}, "rebalance_interval"),
        ({"minimum_weight_change": -0.01}, "minimum_weight_change"),
        ({"minimum_weight_change": 1.01}, "minimum_weight_change"),
    ],
)
def test_rebalancing_controls_are_validated(kwargs, message):
    with pytest.raises(ValueError, match=message):
        VolatilityManagedTrendConfig(**kwargs).validate()
