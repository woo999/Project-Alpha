import pandas as pd
import pytest

from project_alpha.backtest import BacktestConfig, run_long_only_sma, summarize


def test_signal_uses_next_bar_and_charges_costs():
    prices = pd.Series([10, 10, 10, 11, 12, 13, 14], dtype=float)
    config = BacktestConfig(
        fast_window=2,
        slow_window=3,
        fee_rate=0.001,
        slippage_rate=0.001,
    )

    result = run_long_only_sma(prices, config)

    first_signal = result.index[result["signal"] == 1.0][0]
    assert result.loc[first_signal, "position"] == 0.0
    assert result["cost"].sum() > 0
    assert summarize(result)["trades"] >= 1


def test_rejects_invalid_configuration():
    prices = pd.Series(range(1, 20), dtype=float)
    with pytest.raises(ValueError):
        run_long_only_sma(prices, BacktestConfig(fast_window=5, slow_window=5))


def test_rejects_short_history():
    prices = pd.Series([1, 2, 3], dtype=float)
    with pytest.raises(ValueError):
        run_long_only_sma(prices, BacktestConfig(fast_window=2, slow_window=4))
