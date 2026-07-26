"""Small, auditable backtest primitives for Project Alpha."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class BacktestConfig:
    fast_window: int = 20
    slow_window: int = 100
    fee_rate: float = 0.001
    slippage_rate: float = 0.0005

    def validate(self) -> None:
        if self.fast_window < 1:
            raise ValueError("fast_window must be positive")
        if self.slow_window <= self.fast_window:
            raise ValueError("slow_window must be greater than fast_window")
        if self.fee_rate < 0 or self.slippage_rate < 0:
            raise ValueError("cost rates cannot be negative")


def run_long_only_sma(prices: pd.Series, config: BacktestConfig) -> pd.DataFrame:
    """Backtest a long/cash SMA regime using next-bar execution."""
    config.validate()
    clean = pd.to_numeric(prices, errors="coerce").dropna().astype(float)
    if len(clean) <= config.slow_window:
        raise ValueError("not enough price observations")
    if (clean <= 0).any():
        raise ValueError("prices must be positive")

    frame = pd.DataFrame({"close": clean})
    frame["fast_sma"] = frame["close"].rolling(config.fast_window).mean()
    frame["slow_sma"] = frame["close"].rolling(config.slow_window).mean()
    frame["signal"] = (frame["fast_sma"] > frame["slow_sma"]).astype(float)
    frame["position"] = frame["signal"].shift(1).fillna(0.0)
    frame["asset_return"] = frame["close"].pct_change().fillna(0.0)
    frame["turnover"] = (
        frame["position"].diff().abs().fillna(frame["position"].abs())
    )
    frame["cost"] = frame["turnover"] * (
        config.fee_rate + config.slippage_rate
    )
    frame["strategy_return"] = (
        frame["position"] * frame["asset_return"] - frame["cost"]
    )
    frame["equity"] = (1.0 + frame["strategy_return"]).cumprod()
    frame["peak"] = frame["equity"].cummax()
    frame["drawdown"] = frame["equity"] / frame["peak"] - 1.0
    return frame


def summarize(result: pd.DataFrame) -> dict[str, float]:
    """Return the first risk metrics used by the validation pipeline."""
    if result.empty:
        raise ValueError("result cannot be empty")
    return {
        "total_return": float(result["equity"].iloc[-1] - 1.0),
        "max_drawdown": float(result["drawdown"].min()),
        "trades": float(result["position"].diff().abs().fillna(0.0).sum()),
    }
