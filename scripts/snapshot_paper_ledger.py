"""Create an offline, tamper-evident paper-ledger checkpoint."""

from __future__ import annotations

import argparse
from pathlib import Path

from project_alpha.paper_snapshot_io import build_snapshot, write_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a preregistered paper ledger and write a deterministic "
            "JSON checkpoint. This command cannot place orders."
        )
    )
    parser.add_argument("preregistration", type=Path)
    parser.add_argument("observations", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    snapshot = build_snapshot(args.preregistration, args.observations)
    write_snapshot(snapshot, args.output)
    print(
        f"wrote {snapshot.observation_count} observations; "
        f"ledger_hash={snapshot.ledger_hash}"
    )


if __name__ == "__main__":
    main()

