"""Validate Mitake exports and safely append offline paper observations."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from project_alpha.mitake import common_bars_after, load_mitake_daily_export
from project_alpha.paper_audit import build_batch_audit
from project_alpha.paper_daily import (
    append_common_daily_bars,
    load_paper_actions,
    validate_action_freshness,
)
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
        "--primary-actions-verified-through",
        type=date.fromisoformat,
        help="official-source coverage date for the primary action file",
    )
    parser.add_argument(
        "--defensive-actions-verified-through",
        type=date.fromisoformat,
        help="official-source coverage date for the defensive action file",
    )
    parser.add_argument(
        "--audit-output",
        type=Path,
        help="required with --write when new observations are appended",
    )
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
    prior_ledger_hash = ledger.ledger_hash
    observation_count_before = len(ledger.observations)
    last_observed_on = ledger.observations[-1].observed_on
    primary = load_mitake_daily_export(
        args.primary_export, expected_symbol=ledger.spec.primary_symbol
    )
    defensive = load_mitake_daily_export(
        args.defensive_export, expected_symbol=ledger.spec.defensive_symbol
    )
    pairs = common_bars_after(primary, defensive, after=last_observed_on)
    primary_actions = load_paper_actions(args.primary_actions)
    defensive_actions = load_paper_actions(args.defensive_actions)
    result = append_common_daily_bars(
        ledger,
        pairs,
        primary_actions=primary_actions,
        defensive_actions=defensive_actions,
    )
    audit = None
    action_freshness_verified = False
    if result.appended_dates:
        if args.write and (
            args.primary_actions_verified_through is None
            or args.defensive_actions_verified_through is None
        ):
            raise ValueError(
                "both corporate-action verification dates are required with --write"
            )
        if (
            args.primary_actions_verified_through is not None
            and args.defensive_actions_verified_through is not None
        ):
            required_through = result.appended_dates[-1]
            validate_action_freshness(
                primary_actions,
                verified_through=args.primary_actions_verified_through,
                required_through=required_through,
                label=ledger.spec.primary_symbol,
            )
            validate_action_freshness(
                defensive_actions,
                verified_through=args.defensive_actions_verified_through,
                required_through=required_through,
                label=ledger.spec.defensive_symbol,
            )
            action_freshness_verified = True
        audit = build_batch_audit(
            candidate_id=ledger.spec.candidate_id,
            prior_ledger_hash=prior_ledger_hash,
            new_ledger_hash=ledger.ledger_hash,
            observation_count_before=observation_count_before,
            observation_count_after=len(ledger.observations),
            appended_dates=result.appended_dates,
            primary_export_path=args.primary_export,
            defensive_export_path=args.defensive_export,
            primary_actions_path=args.primary_actions,
            defensive_actions_path=args.defensive_actions,
            primary_bars=primary,
            defensive_bars=defensive,
            primary_actions=primary_actions,
            defensive_actions=defensive_actions,
            primary_actions_verified_through=(
                args.primary_actions_verified_through
                or date.min
            ),
            defensive_actions_verified_through=(
                args.defensive_actions_verified_through
                or date.min
            ),
        )
    if args.write and result.appended_dates:
        if args.audit_output is None:
            raise ValueError("--audit-output is required with --write")
        if args.audit_output.exists():
            raise ValueError("audit output already exists; refusing to overwrite history")
        write_checkpoint(
            ledger,
            args.observations,
            args.snapshot,
            additional_text_files={
                args.audit_output: json.dumps(
                    audit, indent=2, sort_keys=True
                )
                + "\n"
            },
        )
    output = {
        "mode": "paper_only_no_broker",
        "write_requested": args.write,
        "appended_count": len(result.appended_dates),
        "appended_dates": [value.isoformat() for value in result.appended_dates],
        "stopped_before_rebalance": result.stopped_before_rebalance,
        "observation_count": len(ledger.observations),
        "last_observed_on": ledger.observations[-1].observed_on.isoformat(),
        "ledger_hash": ledger.ledger_hash,
        "source_audit": audit,
        "action_freshness_verified": action_freshness_verified,
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
