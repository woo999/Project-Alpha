"""Print authenticated Project Alpha paper status; never places orders."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from project_alpha.paper_snapshot_io import load_paper_ledger, load_snapshot
from project_alpha.paper_status import build_paper_status


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only paper status with snapshot verification."
    )
    parser.add_argument("preregistration", type=Path)
    parser.add_argument("observations", type=Path)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    ledger = load_paper_ledger(args.preregistration, args.observations)
    ledger.verify_snapshot(load_snapshot(args.snapshot))
    print(
        json.dumps(
            build_paper_status(ledger).to_dict(),
            indent=2,
            sort_keys=True,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
