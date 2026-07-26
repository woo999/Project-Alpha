"""Performance metrics and fail-closed strategy acceptance gates."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd


@dataclass(frozen=True)
class PerformanceMetrics:
    observations: int
    total_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    profit_factor: float
    hit_rate: float
    exposure: float
    trades: float


@dataclass(frozen=True)
class AcceptanceCriteria:
    minimum_observations: int = 63
    minimum_total_return: float = 0.0
    minimum_sharpe: float = 0.50
    minimum_calmar: float = 0.50
    minimum_profit_factor: float = 1.05
    maximum_drawdown: float = 0.20
    minimum_trades: float = 5.0

    def validate(self) -> None:
        if self.minimum_observations < 2:
            raise ValueError("minimum_observations must be at least two")
        if self.maximum_drawdown <= 0.0 or self.maximum_drawdown >= 1.0:
            raise ValueError("maximum_drawdown must be between zero and one")
        if self.minimum_trades < 0.0:
            raise ValueError("minimum_trades cannot be negative")


@dataclass(frozen=True)
class GateDecision:
    passed: bool
    reasons: tuple[str, ...]


def calculate_performance_metrics(
    result: pd.DataFrame,
    *,
    periods_per_year: int = 252,
    annual_risk_free_rate: float = 0.0,
) -> PerformanceMetrics:
    """Calculate cost-adjusted risk and return metrics from a backtest."""
    required = {"strategy_return", "equity", "drawdown", "position"}
    missing = required.difference(result.columns)
    if missing:
        raise ValueError(f"result is missing columns: {sorted(missing)}")
    if result.empty:
        raise ValueError("result cannot be empty")
    if periods_per_year < 1:
        raise ValueError("periods_per_year must be positive")

    returns = pd.to_numeric(result["strategy_return"], errors="raise").astype(float)
    if returns.isna().any() or not returns.map(math.isfinite).all():
        raise ValueError("strategy returns must be finite")
    observations = len(returns)
    ending_equity = float((1.0 + returns).prod())
    total_return = ending_equity - 1.0
    annualized_return = (
        ending_equity ** (periods_per_year / observations) - 1.0
        if ending_equity > 0.0
        else -1.0
    )

    per_period_risk_free = annual_risk_free_rate / periods_per_year
    excess = returns - per_period_risk_free
    volatility = float(excess.std(ddof=0))
    annualized_volatility = volatility * math.sqrt(periods_per_year)
    sharpe = (
        float(excess.mean()) / volatility * math.sqrt(periods_per_year)
        if volatility > 0.0
        else (math.inf if float(excess.mean()) > 0.0 else 0.0)
    )

    downside = excess.clip(upper=0.0)
    downside_deviation = math.sqrt(float((downside**2).mean()))
    sortino = (
        float(excess.mean()) / downside_deviation * math.sqrt(periods_per_year)
        if downside_deviation > 0.0
        else (math.inf if float(excess.mean()) > 0.0 else 0.0)
    )

    max_drawdown = float(pd.to_numeric(result["drawdown"]).min())
    calmar = (
        annualized_return / abs(max_drawdown)
        if max_drawdown < 0.0
        else (math.inf if annualized_return > 0.0 else 0.0)
    )

    gains = float(returns[returns > 0.0].sum())
    losses = abs(float(returns[returns < 0.0].sum()))
    profit_factor = gains / losses if losses > 0.0 else (math.inf if gains > 0.0 else 0.0)
    active_returns = returns[returns != 0.0]
    hit_rate = (
        float((active_returns > 0.0).mean()) if not active_returns.empty else 0.0
    )
    position = pd.to_numeric(result["position"], errors="raise").astype(float)
    exposure = float(position.abs().mean())
    trades = float(position.diff().abs().fillna(position.abs()).sum())

    return PerformanceMetrics(
        observations=observations,
        total_return=total_return,
        annualized_return=annualized_return,
        annualized_volatility=annualized_volatility,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_drawdown,
        calmar=calmar,
        profit_factor=profit_factor,
        hit_rate=hit_rate,
        exposure=exposure,
        trades=trades,
    )


def evaluate_acceptance(
    metrics: PerformanceMetrics,
    criteria: AcceptanceCriteria | None = None,
) -> GateDecision:
    """Return every failed rule; passing requires all rules simultaneously."""
    rules = criteria or AcceptanceCriteria()
    rules.validate()
    reasons: list[str] = []

    if metrics.observations < rules.minimum_observations:
        reasons.append(
            f"observations {metrics.observations} < {rules.minimum_observations}"
        )
    if metrics.total_return <= rules.minimum_total_return:
        reasons.append(
            f"total_return {metrics.total_return:.4f} <= "
            f"{rules.minimum_total_return:.4f}"
        )
    if metrics.sharpe < rules.minimum_sharpe:
        reasons.append(f"sharpe {metrics.sharpe:.3f} < {rules.minimum_sharpe:.3f}")
    if metrics.calmar < rules.minimum_calmar:
        reasons.append(f"calmar {metrics.calmar:.3f} < {rules.minimum_calmar:.3f}")
    if metrics.profit_factor < rules.minimum_profit_factor:
        reasons.append(
            f"profit_factor {metrics.profit_factor:.3f} < "
            f"{rules.minimum_profit_factor:.3f}"
        )
    if metrics.max_drawdown < -rules.maximum_drawdown:
        reasons.append(
            f"max_drawdown {metrics.max_drawdown:.3f} < "
            f"{-rules.maximum_drawdown:.3f}"
        )
    if metrics.trades < rules.minimum_trades:
        reasons.append(f"trades {metrics.trades:.1f} < {rules.minimum_trades:.1f}")

    return GateDecision(passed=not reasons, reasons=tuple(reasons))
