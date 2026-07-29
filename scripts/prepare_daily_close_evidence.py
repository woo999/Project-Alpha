"""Reconcile latest Mitake closes with free official closing data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from project_alpha.daily_close_evidence import prepare_daily_close_evidence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create official close evidence for paper tracking only; "
            "never connects to a broker or places orders."
        )
    )
    parser.add_argument("primary_export", type=Path)
    parser.add_argument("defensive_export", type=Path)
    parser.add_argument("output_root", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = prepare_daily_close_evidence(
        primary_export_path=args.primary_export,
        defensive_export_path=args.defensive_export,
        output_root=args.output_root,
    )
    print(
        json.dumps(
            {
                "mode": "paper_only_no_broker",
                "output": str(output),
                "files": sorted(item.name for item in output.iterdir()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
