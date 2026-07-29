"""Report whether both free official close feeds cover one paper date."""

from __future__ import annotations

import argparse
from datetime import date
import json

from project_alpha.mitake import load_mitake_daily_export
from project_alpha.official_close import (
    OfficialClose,
    TPEX_DAILY_CLOSE_URL,
    TWSE_DAILY_CLOSE_URL,
    close_readiness_blockers,
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
    parser.add_argument("--primary-export")
    parser.add_argument("--defensive-export")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if bool(args.primary_export) != bool(args.defensive_export):
        raise ValueError(
            "primary and defensive Mitake exports must be supplied together"
        )
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
    official_closes = {"0050": primary, "00719B": defensive}
    export_closes = None
    exports = None
    if args.primary_export:
        primary_export = load_mitake_daily_export(
            args.primary_export,
            expected_symbol="0050",
        )[-1]
        defensive_export = load_mitake_daily_export(
            args.defensive_export,
            expected_symbol="00719B",
        )[-1]
        export_closes = {
            "0050": OfficialClose(
                primary_export.observed_on,
                "0050",
                primary_export.close,
            ),
            "00719B": OfficialClose(
                defensive_export.observed_on,
                "00719B",
                defensive_export.close,
            ),
        }
        exports = {
            symbol: {
                "observed_on": value.observed_on.isoformat(),
                "close": value.close,
            }
            for symbol, value in export_closes.items()
        }
    blockers = close_readiness_blockers(
        expected_date=args.expected_date,
        official_closes=official_closes,
        export_closes=export_closes,
    )
    report = {
        "mode": "paper_only_no_broker",
        "expected_date": args.expected_date.isoformat(),
        "ready": not blockers,
        "blockers": list(blockers),
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
    }
    if exports is not None:
        report["exports"] = exports
    print(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
