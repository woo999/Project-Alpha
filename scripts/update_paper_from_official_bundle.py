"""Atomically append one paper mark from a complete official bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from project_alpha.official_paper_update import append_official_bundle_mark
from project_alpha.paper_snapshot_io import (
    load_authenticated_paper_ledger,
    write_checkpoint,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update paper tracking from one four-source official bundle."
    )
    parser.add_argument("preregistration", type=Path)
    parser.add_argument("observations", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("bundle_dir", type=Path)
    parser.add_argument("primary_actions", type=Path)
    parser.add_argument("defensive_actions", type=Path)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    ledger = load_authenticated_paper_ledger(
        args.preregistration, args.observations, args.snapshot
    )
    audit = append_official_bundle_mark(
        ledger,
        bundle_dir=args.bundle_dir,
        primary_actions_path=args.primary_actions,
        defensive_actions_path=args.defensive_actions,
    )
    if args.write:
        if args.audit_output is None:
            raise ValueError("--audit-output is required with --write")
        if args.audit_output.exists():
            raise ValueError("audit output already exists; refusing to overwrite")
        write_checkpoint(
            ledger,
            args.observations,
            args.snapshot,
            additional_text_files={
                args.audit_output: json.dumps(audit, indent=2, sort_keys=True) + "\n"
            },
        )
    print(
        json.dumps(
            {
                "mode": "paper_only_no_broker",
                "write_requested": args.write,
                "observation_count": len(ledger.observations),
                "last_observed_on": ledger.observations[-1].observed_on.isoformat(),
                "ledger_hash": ledger.ledger_hash,
                "source_audit": audit,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
