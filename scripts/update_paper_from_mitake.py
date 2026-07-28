"""Validate Mitake exports and safely append offline paper observations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from project_alpha.mitake import common_bars_after, load_mitake_daily_export
from project_alpha.paper_daily import append_common_daily_bars, load_paper_actions
from project_alpha.paper_snapshot_io import (
    load_paper_ledger,
    load_snapshot,
    write_checkpoint,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and append paper marks; never connects to a broker."
    )
    parser.add_argument("preregistration", type=Path)
    parser.add_argument("observations", type=Path)
    parser.add_argument("primary_export", type=Path)
    parser.add_argument("defensive_export", type=Path)
    parser.add_argument("primary_actions", type=Path)
    parser.add_argument("defensive_actions", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument(
        "--write",
        action="store_true",
        help="atomically replace the local observation CSV and snapshot",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ledger = load_paper_ledger(args.preregistration, args.observations)
    ledger.verify_snapshot(load_snapshot(args.snapshot))
    last_observed_on = ledger.observations[-1].observed_on
    primary = load_mitake_daily_export(
        args.primary_export, expected_symbol=ledger.spec.primary_symbol
    )
    defensive = load_mitake_daily_export(
        args.defensive_export, expected_symbol=ledger.spec.defensive_symbol
    )
    pairs = common_bars_after(primary, defensive, after=last_observed_on)
    result = append_common_daily_bars(
        ledger,
        pairs,
        primary_actions=load_paper_actions(args.primary_actions),
        defensive_actions=load_paper_actions(args.defensive_actions),
    )
    if args.write and result.appended_dates:
        write_checkpoint(ledger, args.observations, args.snapshot)
    output = {
        "mode": "paper_only_no_broker",
        "write_requested": args.write,
        "appended_count": len(result.appended_dates),
        "appended_dates": [value.isoformat() for value in result.appended_dates],
        "stopped_before_rebalance": result.stopped_before_rebalance,
        "observation_count": len(ledger.observations),
        "last_observed_on": ledger.observations[-1].observed_on.isoformat(),
        "ledger_hash": ledger.ledger_hash,
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
