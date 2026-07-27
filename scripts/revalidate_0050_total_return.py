"""Revalidate predeclared 0050 strategies on the reconstructed total-return series."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

import pandas as pd

from project_alpha.absolute_momentum import (
    AbsoluteMomentumConfig,
    run_absolute_momentum,
)
from project_alpha.backtest import BacktestConfig
from project_alpha.core_protection import CoreProtectionConfig, run_core_protection
from project_alpha.corporate_actions import (
    build_total_return_index,
    load_corporate_actions_csv,
)
from project_alpha.fixed_validation import (
    run_fixed_sma_walk_forward,
    run_fixed_strategy_walk_forward,
)
from project_alpha.risk_managed import (
    VolatilityManagedTrendConfig,
    run_volatility_managed_trend,
)


def load_mitake_close(path: Path) -> pd.Series:
    frame = pd.read_csv(path, sep="\t", skiprows=2, encoding="utf-8-sig")
    frame = frame.loc[frame["日期"].astype(str).str.startswith("'")].copy()
    dates = pd.to_datetime(
        frame["日期"].str.lstrip("'"),
        format="%Y/%m/%d %H:%M",
        errors="raise",
    )
    close = pd.to_numeric(frame["收盤價"], errors="raise").to_numpy()
    return pd.Series(close, index=pd.DatetimeIndex(dates), name="close")


def summarize(result: object) -> dict[str, object]:
    performance = result.aggregate_performance
    benchmark = result.benchmark_report
    return {
        "passed": result.decision.passed,
        "reasons": list(result.decision.reasons),
        "folds": len(result.folds),
        "fold_pass_fraction": result.fold_pass_fraction,
        "positive_fold_fraction": result.positive_fold_fraction,
        "total_return": performance.total_return,
        "annualized_return": performance.annualized_return,
        "sharpe": performance.sharpe,
        "calmar": performance.calmar,
        "maximum_drawdown": performance.max_drawdown,
        "profit_factor": performance.profit_factor,
        "cost_stress_pass_fraction": result.cost_stress_report.pass_fraction,
        "benchmark_passed": result.benchmark_decision.passed,
        "benchmark_total_return": (
            benchmark.benchmark_performance.total_return
        ),
        "benchmark_excess_total_return": benchmark.excess_total_return,
        "benchmark_drawdown_improvement": benchmark.drawdown_improvement,
        "benchmark_sharpe_improvement": benchmark.sharpe_improvement,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("prices", type=Path)
    parser.add_argument("actions", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    raw_prices = load_mitake_close(args.prices)
    actions = load_corporate_actions_csv(
        args.actions, price_index=raw_prices.index
    )
    prices = build_total_return_index(raw_prices, actions)
    common = {"min_train": 1000, "test_size": 250, "step_size": 250}

    strategies = [
        (
            "sma_20_200",
            BacktestConfig(fast_window=20, slow_window=200),
            None,
            200,
        ),
        (
            "price_above_200",
            BacktestConfig(fast_window=1, slow_window=200),
            None,
            200,
        ),
        (
            "absolute_momentum_252_21",
            AbsoluteMomentumConfig(),
            run_absolute_momentum,
            252,
        ),
        (
            "core_70_trend_30",
            CoreProtectionConfig(),
            run_core_protection,
            200,
        ),
        (
            "volatility_12_5_buffered",
            VolatilityManagedTrendConfig(
                target_annualized_volatility=0.125,
                rebalance_interval=5,
                minimum_weight_change=0.05,
            ),
            run_volatility_managed_trend,
            200,
        ),
    ]
    results = {}
    for name, config, runner, minimum_history in strategies:
        if runner is None:
            validation = run_fixed_sma_walk_forward(
                prices, config, **common
            )
        else:
            validation = run_fixed_strategy_walk_forward(
                prices,
                config,
                runner,
                minimum_history=minimum_history,
                **common,
            )
        results[name] = {
            "config": asdict(config),
            "result": summarize(validation),
        }

    report = {
        "status": "REVALIDATION_ONLY",
        "price_basis": "total_return_reconstructed",
        "observations": len(prices),
        "start": str(prices.index[0].date()),
        "end": str(prices.index[-1].date()),
        "parameter_search": False,
        "strategies": results,
        "paper_trading_candidate": any(
            item["result"]["passed"] for item in results.values()
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
