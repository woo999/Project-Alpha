"""Download and reconcile one daily package of free official action data."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from project_alpha.daily_action_evidence import (
    prepare_daily_action_evidence,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare official TWSE/TPEx evidence for paper tracking only; "
            "never connects to a broker or places orders."
        )
    )
    parser.add_argument("verified_through", type=date.fromisoformat)
    parser.add_argument("primary_actions", type=Path)
    parser.add_argument("defensive_actions", type=Path)
    parser.add_argument("output_root", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = prepare_daily_action_evidence(
        verified_through=args.verified_through,
        primary_action_path=args.primary_actions,
        defensive_action_path=args.defensive_actions,
        output_root=args.output_root,
    )
    print(
        json.dumps(
            {
                "mode": "paper_only_no_broker",
                "output": str(output),
                "verified_through": args.verified_through.isoformat(),
                "files": sorted(item.name for item in output.iterdir()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
