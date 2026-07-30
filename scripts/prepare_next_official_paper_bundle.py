"""Prepare official evidence for the next date after an authenticated ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from project_alpha.next_official_bundle import prepare_next_official_paper_bundle
from project_alpha.official_paper_bundle import load_official_paper_bundle
from project_alpha.paper_snapshot_io import load_authenticated_paper_ledger


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover and prepare the next official paper evidence bundle."
    )
    parser.add_argument("preregistration", type=Path)
    parser.add_argument("observations", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("primary_actions", type=Path)
    parser.add_argument("defensive_actions", type=Path)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    ledger = load_authenticated_paper_ledger(
        args.preregistration, args.observations, args.snapshot
    )
    output = prepare_next_official_paper_bundle(
        ledger,
        primary_action_path=args.primary_actions,
        defensive_action_path=args.defensive_actions,
        output_root=args.output_root,
    )
    if output is None:
        result = {
            "mode": "paper_only_no_broker",
            "ready": False,
            "reason": "official sources have no date after the authenticated ledger",
            "last_observed_on": ledger.observations[-1].observed_on.isoformat(),
        }
    else:
        bundle = load_official_paper_bundle(
            output,
            primary_action_path=args.primary_actions,
            defensive_action_path=args.defensive_actions,
        )
        result = {
            "mode": "paper_only_no_broker",
            "ready": True,
            "output": str(output),
            "observed_on": bundle.observed_on.isoformat(),
            "closes": {
                bundle.close.primary.symbol: bundle.close.primary.close,
                bundle.close.defensive.symbol: bundle.close.defensive.close,
            },
        }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
