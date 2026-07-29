"""Report whether both free official close feeds cover one paper date."""

from __future__ import annotations

import argparse
from datetime import date
import json

from project_alpha.official_close import (
    TPEX_DAILY_CLOSE_URL,
    TWSE_DAILY_CLOSE_URL,
    official_close_for_symbol,
)
from project_alpha.official_source import fetch_official_source


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read free official close feeds and report paper-data readiness; "
            "never connects to a broker."
        )
    )
    parser.add_argument("expected_date", type=date.fromisoformat)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    primary_download = fetch_official_source(TWSE_DAILY_CLOSE_URL)
    defensive_download = fetch_official_source(TPEX_DAILY_CLOSE_URL)
    primary = official_close_for_symbol(
        primary_download.content,
        source_url=primary_download.final_url,
        symbol="0050",
    )
    defensive = official_close_for_symbol(
        defensive_download.content,
        source_url=defensive_download.final_url,
        symbol="00719B",
    )
    ready = (
        primary.observed_on == args.expected_date
        and defensive.observed_on == args.expected_date
    )
    print(
        json.dumps(
            {
                "mode": "paper_only_no_broker",
                "expected_date": args.expected_date.isoformat(),
                "ready": ready,
                "sources": {
                    "0050": {
                        "observed_on": primary.observed_on.isoformat(),
                        "close": primary.close,
                        "url": primary_download.final_url,
                    },
                    "00719B": {
                        "observed_on": defensive.observed_on.isoformat(),
                        "close": defensive.close,
                        "url": defensive_download.final_url,
                    },
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
