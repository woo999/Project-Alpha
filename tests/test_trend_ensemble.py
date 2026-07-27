import pandas as pd
import pytest

from project_alpha.trend_ensemble import (
    TrendEnsembleConfig,
    run_trend_ensemble,
)


def test_exposure_is_fractional_and_unlevered():
    dates = pd.date_range("2020-01-01", periods=80, freq="D")
    prices = pd.Series(
        [100.0 + index * 0.2 + (5.0 if index > 50 else 0.0)
         for index in range(80)],
        index=dates,
    )
    config = TrendEnsembleConfig(
        windows=(10, 20, 40),
        rebalance_interval=1,
        fee_rate=0.0,
        slippage_rate=0.0,
    )

    result = run_trend_ensemble(prices, config)

    assert result["position"].between(0.0, 1.0).all()
    scaled = result["position"] * 3
    assert (scaled.round(10) == scaled.round()).all()


def test_signal_is_lagged_one_day():
    dates = pd.date_range("2020-01-01", periods=8, freq="D")
    prices = pd.Series(
        [10.0, 10.0, 10.0, 10.0, 12.0, 12.0, 12.0, 12.0],
        index=dates,
    )
    config = TrendEnsembleConfig(
        windows=(2, 3),
        rebalance_interval=1,
        fee_rate=0.0,
        slippage_rate=0.0,
    )

    result = run_trend_ensemble(prices, config)

    assert result.loc[dates[4], "position"] == pytest.approx(0.0)
    assert result.loc[dates[5], "position"] == pytest.approx(1.0)


@pytest.mark.parametrize(
    "windows",
    [(20,), (1, 20), (20, 10), (10, 10)],
)
def test_invalid_windows_are_rejected(windows):
    with pytest.raises(ValueError):
        TrendEnsembleConfig(windows=windows).validate()
