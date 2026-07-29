"""Save a bounded raw response from an approved official source."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from project_alpha.official_source import fetch_official_source


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download free official evidence only; does not connect to a broker "
            "or place orders."
        )
    )
    parser.add_argument("official_source_url")
    parser.add_argument("output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = fetch_official_source(args.official_source_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as handle:
        handle.write(result.content)
    print(
        json.dumps(
            {
                "mode": "paper_only_no_broker",
                "output": str(args.output),
                "final_url": result.final_url,
                "content_type": result.content_type,
                "byte_count": len(result.content),
                "sha256": result.sha256,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
