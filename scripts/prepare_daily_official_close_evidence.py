"""Prepare official-only daily close evidence for paper tracking."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from project_alpha.daily_official_close_evidence import (
    load_daily_official_close_evidence,
    prepare_daily_official_close_evidence,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare free official close evidence for paper tracking only; "
            "never connects to a broker or places orders."
        )
    )
    parser.add_argument("expected_date", type=date.fromisoformat)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    output = prepare_daily_official_close_evidence(
        expected_date=args.expected_date,
        output_root=args.output_root,
    )
    evidence = load_daily_official_close_evidence(output)
    print(
        json.dumps(
            {
                "mode": "paper_only_no_broker",
                "output": str(output),
                "observed_on": evidence.observed_on.isoformat(),
                "closes": {
                    evidence.primary.symbol: evidence.primary.close,
                    evidence.defensive.symbol: evidence.defensive.close,
                },
                "files": sorted(item.name for item in output.iterdir()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
