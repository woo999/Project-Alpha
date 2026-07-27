"""Core holding with a limited, unlevered trend-protection sleeve."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class CoreProtectionConfig:
    trend_window: int = 200
    core_weight: float = 0.70
    rebalance_interval: int = 5
    fee_rate: float = 0.001
    slippage_rate: float = 0.0005

    def validate(self) -> None:
        if self.trend_window < 2:
            raise ValueError("trend_window must be at least two")
        if not 0.0 <= self.core_weight <= 1.0:
            raise ValueError("core_weight must be in [0, 1]")
        if self.rebalance_interval < 1:
            raise ValueError("rebalance_interval must be positive")
        if self.fee_rate < 0.0 or self.slippage_rate < 0.0:
            raise ValueError("cost rates cannot be negative")

    @property
    def minimum_history(self) -> int:
        return self.trend_window


def run_core_protection(
    prices: pd.Series,
    config: CoreProtectionConfig,
) -> pd.DataFrame:
    """Keep the core invested and switch only the protection sleeve."""
    config.validate()
    clean = pd.to_numeric(prices, errors="coerce").dropna().astype(float)
    if len(clean) <= config.minimum_history:
        raise ValueError("not enough price observations")
    if (clean <= 0.0).any():
        raise ValueError("prices must be positive")

    frame = pd.DataFrame({"close": clean})
    frame["asset_return"] = frame["close"].pct_change().fillna(0.0)
    frame["trend_average"] = frame["close"].rolling(
        config.trend_window
    ).mean()
    trend_on = (frame["close"] > frame["trend_average"]).astype(float)
    desired_position = (
        config.core_weight + (1.0 - config.core_weight) * trend_on
    )
    available_target = desired_position.shift(1).fillna(config.core_weight)

    current_position = config.core_weight
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
