"""Validate Mitake exports and safely append offline paper observations."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from project_alpha.action_verification import load_action_verification
from project_alpha.action_schedule import verify_official_action_day
from project_alpha.daily_action_evidence import load_daily_action_evidence
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
        "--action-evidence-dir",
        type=Path,
        help="complete atomic daily evidence package for both symbols",
    )
    parser.add_argument(
        "--primary-action-verification",
        type=Path,
        help="JSON proof binding primary actions to an official source",
    )
    parser.add_argument(
        "--defensive-action-verification",
        type=Path,
        help="JSON proof binding defensive actions to an official source",
    )
    parser.add_argument(
        "--primary-action-source",
        type=Path,
        help="saved raw official response bound by the primary proof",
    )
    parser.add_argument(
        "--defensive-action-source",
        type=Path,
        help="saved raw official response bound by the defensive proof",
    )
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
    primary_verified_through = args.primary_actions_verified_through
    defensive_verified_through = args.defensive_actions_verified_through
    primary_verification_path = args.primary_action_verification
    defensive_verification_path = args.defensive_action_verification
    primary_source_path = args.primary_action_source
    defensive_source_path = args.defensive_action_source
    if result.appended_dates:
        if args.action_evidence_dir is not None:
            if any(
                value is not None
                for value in (
                    args.primary_action_verification,
                    args.defensive_action_verification,
                    args.primary_action_source,
                    args.defensive_action_source,
                    args.primary_actions_verified_through,
                    args.defensive_actions_verified_through,
                )
            ):
                raise ValueError(
                    "--action-evidence-dir cannot be mixed with individual "
                    "action verification options"
                )
            package = load_daily_action_evidence(
                args.action_evidence_dir,
                primary_action_path=args.primary_actions,
                defensive_action_path=args.defensive_actions,
            )
            primary_verification_path = package.primary_verification_path
            defensive_verification_path = package.defensive_verification_path
            primary_source_path = package.primary_source_path
            defensive_source_path = package.defensive_source_path
            primary_proof = package.primary_verification
            defensive_proof = package.defensive_verification
            primary_verified_through = package.verified_through
            defensive_verified_through = package.verified_through
        if primary_verification_path is not None and args.action_evidence_dir is None:
            if primary_source_path is None:
                raise ValueError("primary official action source file is required")
            primary_proof = load_action_verification(
                primary_verification_path,
                action_path=args.primary_actions,
                source_path=primary_source_path,
                expected_symbol=ledger.spec.primary_symbol,
            )
            primary_verified_through = primary_proof.verified_through
        if (
            defensive_verification_path is not None
            and args.action_evidence_dir is None
        ):
            if defensive_source_path is None:
                raise ValueError("defensive official action source file is required")
            defensive_proof = load_action_verification(
                defensive_verification_path,
                action_path=args.defensive_actions,
                source_path=defensive_source_path,
                expected_symbol=ledger.spec.defensive_symbol,
            )
            defensive_verified_through = defensive_proof.verified_through
        if args.write and (
            primary_verification_path is None
            or defensive_verification_path is None
        ):
            raise ValueError(
                "both hash-bound action verification documents are required with --write"
            )
        if (
            primary_verified_through is not None
            and defensive_verified_through is not None
        ):
            required_through = result.appended_dates[-1]
            validate_action_freshness(
                primary_actions,
                verified_through=primary_verified_through,
                required_through=required_through,
                label=ledger.spec.primary_symbol,
            )
            validate_action_freshness(
                defensive_actions,
                verified_through=defensive_verified_through,
                required_through=required_through,
                label=ledger.spec.defensive_symbol,
            )
            if (
                primary_source_path is not None
                and defensive_source_path is not None
                and primary_verification_path is not None
                and defensive_verification_path is not None
            ):
                verify_official_action_day(
                    primary_source_path,
                    source_url=primary_proof.source_url,
                    symbol=ledger.spec.primary_symbol,
                    event_date=required_through,
                    actions=primary_actions,
                )
                verify_official_action_day(
                    defensive_source_path,
                    source_url=defensive_proof.source_url,
                    symbol=ledger.spec.defensive_symbol,
                    event_date=required_through,
                    actions=defensive_actions,
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
                primary_verified_through or date.min
            ),
            defensive_actions_verified_through=(
                defensive_verified_through or date.min
            ),
            primary_action_verification_path=primary_verification_path,
            defensive_action_verification_path=defensive_verification_path,
            primary_action_source_path=primary_source_path,
            defensive_action_source_path=defensive_source_path,
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
