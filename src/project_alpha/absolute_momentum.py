"""Unlevered, low-turnover absolute-momentum strategy."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class AbsoluteMomentumConfig:
    lookback: int = 252
    rebalance_interval: int = 21
    fee_rate: float = 0.001
    slippage_rate: float = 0.0005

    def validate(self) -> None:
        if self.lookback < 2:
            raise ValueError("lookback must be at least two")
        if self.rebalance_interval < 1:
            raise ValueError("rebalance_interval must be positive")
        if self.fee_rate < 0.0 or self.slippage_rate < 0.0:
            raise ValueError("cost rates cannot be negative")

    @property
    def minimum_history(self) -> int:
        return self.lookback


def run_absolute_momentum(
    prices: pd.Series,
    config: AbsoluteMomentumConfig,
) -> pd.DataFrame:
    """Hold the asset when its trailing return is positive, checked monthly."""
    config.validate()
    clean = pd.to_numeric(prices, errors="coerce").dropna().astype(float)
    if len(clean) <= config.minimum_history:
        raise ValueError("not enough price observations")
    if (clean <= 0.0).any():
        raise ValueError("prices must be positive")

    frame = pd.DataFrame({"close": clean})
    frame["asset_return"] = frame["close"].pct_change().fillna(0.0)
    frame["momentum"] = frame["close"] / frame["close"].shift(
        config.lookback
    ) - 1.0
    available_target = (
        (frame["momentum"] > 0.0).astype(float).shift(1).fillna(0.0)
    )

    current_position = 0.0
    positions: list[float] = []
    for offset, target in enumerate(available_target):
        if offset % config.rebalance_interval == 0:
            current_position = float(target)
        positions.append(current_position)
    frame["position"] = positions
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
