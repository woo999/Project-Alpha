"""Validate two Mitake daily exports and print the latest common close."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from project_alpha.mitake import latest_common_bar, load_mitake_daily_export


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate local Mitake exports; this command cannot trade."
    )
    parser.add_argument("primary", type=Path)
    parser.add_argument("defensive", type=Path)
    parser.add_argument("--after", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    primary = load_mitake_daily_export(args.primary, expected_symbol="0050")
    defensive = load_mitake_daily_export(
        args.defensive, expected_symbol="00719B"
    )
    first, second = latest_common_bar(primary, defensive, after=args.after)
    print(
        f"{first.observed_on.isoformat()},"
        f"0050={first.close:.4f},00719B={second.close:.4f}"
    )


if __name__ == "__main__":
    main()
