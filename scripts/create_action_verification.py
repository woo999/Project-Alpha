"""Create a deterministic offline proof for a reviewed corporate-action file."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from project_alpha.action_verification import build_action_verification


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Bind a reviewed official source, coverage date, and action-file hash; "
            "does not connect to a broker or place orders."
        )
    )
    parser.add_argument("symbol")
    parser.add_argument("verified_through", type=date.fromisoformat)
    parser.add_argument("action_file", type=Path)
    parser.add_argument("official_source_file", type=Path)
    parser.add_argument("official_source_url")
    parser.add_argument("output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_action_verification(
        symbol=args.symbol,
        verified_through=args.verified_through,
        action_path=args.action_file,
        source_path=args.official_source_file,
        source_url=args.official_source_url,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        json.dumps(
            {
                "mode": "paper_only_no_broker",
                "output": str(args.output),
                "symbol": payload["symbol"],
                "verified_through": payload["verified_through"],
                "action_file_sha256": payload["action_file_sha256"],
                "source_file_sha256": payload["source_file_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
