"""Prepare one atomic four-source official evidence bundle."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from project_alpha.official_paper_bundle import (
    load_official_paper_bundle,
    prepare_official_paper_bundle,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare official evidence for paper tracking only."
    )
    parser.add_argument("observed_on", type=date.fromisoformat)
    parser.add_argument("primary_actions", type=Path)
    parser.add_argument("defensive_actions", type=Path)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    output = prepare_official_paper_bundle(
        observed_on=args.observed_on,
        primary_action_path=args.primary_actions,
        defensive_action_path=args.defensive_actions,
        output_root=args.output_root,
    )
    loaded = load_official_paper_bundle(
        output,
        primary_action_path=args.primary_actions,
        defensive_action_path=args.defensive_actions,
    )
    print(
        json.dumps(
            {
                "mode": "paper_only_no_broker",
                "output": str(output),
                "observed_on": loaded.observed_on.isoformat(),
                "closes": {
                    loaded.close.primary.symbol: loaded.close.primary.close,
                    loaded.close.defensive.symbol: loaded.close.defensive.close,
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
