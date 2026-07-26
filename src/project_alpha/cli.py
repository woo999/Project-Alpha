"""Command-line entry point for offline Project Alpha validation."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import sys
from typing import Any, Sequence

from project_alpha.backtest import BacktestConfig
from project_alpha.data_io import load_price_csv
from project_alpha.walk_forward import run_walk_forward_validation


DEFAULT_WINDOWS = ((5, 20), (10, 30), (15, 40), (20, 50), (15, 60))


def _candidate(value: str) -> tuple[int, int]:
    try:
        fast_text, slow_text = value.split(":", maxsplit=1)
        fast, slow = int(fast_text), int(slow_text)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(
            "candidate must use FAST:SLOW, for example 10:30"
        ) from exc
    config = BacktestConfig(fast_window=fast, slow_window=slow)
    try:
        config.validate()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return fast, slow


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run research-only walk-forward validation on a local CSV."
    )
    parser.add_argument("csv", type=Path)
    parser.add_argument("--timestamp-column", default="timestamp")
    parser.add_argument("--price-column", default="close")
    parser.add_argument("--min-train", type=int, default=504)
    parser.add_argument("--test-size", type=int, default=63)
    parser.add_argument("--periods-per-year", type=int, default=252)
    parser.add_argument("--fee-rate", type=float, default=0.001)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument(
        "--candidate",
        action="append",
        type=_candidate,
        metavar="FAST:SLOW",
        help="repeat to replace the default SMA window candidates",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.min_train < 1 or args.test_size < 1:
        parser.error("min-train and test-size must be positive")
    if args.periods_per_year < 1:
        parser.error("periods-per-year must be positive")
    if args.fee_rate < 0.0 or args.slippage_rate < 0.0:
        parser.error("fee-rate and slippage-rate cannot be negative")

    windows = args.candidate or list(DEFAULT_WINDOWS)
    candidates = [
        BacktestConfig(
            fast_window=fast,
            slow_window=slow,
            fee_rate=args.fee_rate,
            slippage_rate=args.slippage_rate,
        )
        for fast, slow in windows
    ]

    try:
        prices = load_price_csv(
            args.csv,
            timestamp_column=args.timestamp_column,
            price_column=args.price_column,
        )
        result = run_walk_forward_validation(
            prices,
            candidates,
            min_train=args.min_train,
            test_size=args.test_size,
            periods_per_year=args.periods_per_year,
        )
    except (OSError, TypeError, ValueError) as exc:
        print(f"validation_error: {exc}", file=sys.stderr)
        return 2

    report = {
        "mode": "research_only",
        "passed": result.decision.passed,
        "reasons": result.decision.reasons,
        "fold_count": len(result.folds),
        "fold_pass_fraction": result.fold_pass_fraction,
        "positive_fold_fraction": result.positive_fold_fraction,
        "aggregate_performance": asdict(result.aggregate_performance),
        "folds": [
            {
                "train_end": str(fold.train_end),
                "test_start": str(fold.test_start),
                "selected_config": asdict(fold.selected_config),
                "passed": fold.decision.passed,
                "reasons": fold.decision.reasons,
            }
            for fold in result.folds
        ],
    }
    print(json.dumps(_json_safe(report), indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
