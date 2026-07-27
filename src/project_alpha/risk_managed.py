"""Unlevered volatility-managed trend strategy."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd


@dataclass(frozen=True)
class VolatilityManagedTrendConfig:
    trend_window: int = 200
    volatility_window: int = 20
    target_annualized_volatility: float = 0.15
    periods_per_year: int = 252
    maximum_exposure: float = 1.0
    fee_rate: float = 0.001
    slippage_rate: float = 0.0005

    def validate(self) -> None:
        if self.trend_window < 2 or self.volatility_window < 2:
            raise ValueError("trend and volatility windows must be at least two")
        if self.target_annualized_volatility <= 0.0:
            raise ValueError("target volatility must be positive")
        if self.periods_per_year < 1:
            raise ValueError("periods_per_year must be positive")
        if not 0.0 < self.maximum_exposure <= 1.0:
            raise ValueError("maximum_exposure must be in (0, 1]")
        if self.fee_rate < 0.0 or self.slippage_rate < 0.0:
            raise ValueError("cost rates cannot be negative")

    @property
    def minimum_history(self) -> int:
        return max(self.trend_window, self.volatility_window)


def run_volatility_managed_trend(
    prices: pd.Series,
    config: VolatilityManagedTrendConfig,
) -> pd.DataFrame:
    """Hold a volatility-scaled long position only above the trend average."""
    config.validate()
    clean = pd.to_numeric(prices, errors="coerce").dropna().astype(float)
    if len(clean) <= config.minimum_history:
        raise ValueError("not enough price observations")
    if (clean <= 0.0).any():
        raise ValueError("prices must be positive")

    frame = pd.DataFrame({"close": clean})
    frame["asset_return"] = frame["close"].pct_change().fillna(0.0)
    frame["trend_average"] = frame["close"].rolling(config.trend_window).mean()
    frame["realized_volatility"] = (
        frame["asset_return"]
        .rolling(config.volatility_window)
        .std(ddof=0)
        * math.sqrt(config.periods_per_year)
    )
    trend_signal = (frame["close"] > frame["trend_average"]).astype(float)
    volatility_weight = (
        config.target_annualized_volatility / frame["realized_volatility"]
    ).clip(lower=0.0, upper=config.maximum_exposure)
    desired_position = (trend_signal * volatility_weight).fillna(0.0)

    # Both trend and volatility estimates are shifted before earning returns.
    frame["position"] = desired_position.shift(1).fillna(0.0)
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
