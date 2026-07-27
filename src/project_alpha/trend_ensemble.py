"""Unlevered multi-horizon trend ensemble with gradual exposure changes."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TrendEnsembleConfig:
    windows: tuple[int, ...] = (50, 100, 200)
    rebalance_interval: int = 5
    fee_rate: float = 0.001
    slippage_rate: float = 0.0005

    def validate(self) -> None:
        if len(self.windows) < 2:
            raise ValueError("at least two trend windows are required")
        if any(window < 2 for window in self.windows):
            raise ValueError("trend windows must be at least two")
        if tuple(sorted(set(self.windows))) != self.windows:
            raise ValueError("trend windows must be unique and increasing")
        if self.rebalance_interval < 1:
            raise ValueError("rebalance_interval must be positive")
        if self.fee_rate < 0.0 or self.slippage_rate < 0.0:
            raise ValueError("cost rates cannot be negative")

    @property
    def minimum_history(self) -> int:
        return max(self.windows)


def run_trend_ensemble(
    prices: pd.Series,
    config: TrendEnsembleConfig,
) -> pd.DataFrame:
    """Allocate equally across trend sleeves, using only prior-day signals."""
    config.validate()
    clean = pd.to_numeric(prices, errors="coerce").dropna().astype(float)
    if len(clean) <= config.minimum_history:
        raise ValueError("not enough price observations")
    if (clean <= 0.0).any():
        raise ValueError("prices must be positive")

    frame = pd.DataFrame({"close": clean})
    frame["asset_return"] = frame["close"].pct_change().fillna(0.0)
    signals = []
    for window in config.windows:
        average = frame["close"].rolling(window).mean()
        signals.append((frame["close"] > average).astype(float))
    desired = sum(signals) / len(signals)
    available_target = desired.shift(1).fillna(0.0)

    position = 0.0
    positions: list[float] = []
    for offset, target in enumerate(available_target):
        if offset % config.rebalance_interval == 0:
            position = float(target)
        positions.append(position)
    frame["position"] = positions
    if (frame["position"] < 0.0).any() or (frame["position"] > 1.0).any():
        raise RuntimeError("trend ensemble created leveraged exposure")
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

