"""Report whether both free official close feeds cover one paper date."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from project_alpha.mitake import (
    load_mitake_daily_export,
    single_common_bar_after,
)
from project_alpha.official_close import (
    OfficialClose,
    TPEX_DAILY_CLOSE_URL,
    TWSE_DAILY_CLOSE_URL,
    close_readiness_blockers,
    official_close_for_symbol,
)
from project_alpha.official_source import fetch_official_source
from project_alpha.paper_snapshot_io import load_authenticated_paper_ledger


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=PROJECT_ROOT / "research/preregistration.json",
    )
    parser.add_argument(
        "--observations",
        type=Path,
        default=PROJECT_ROOT / "data/paper_observations.csv",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=PROJECT_ROOT / "research/paper_snapshot.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ledger = load_authenticated_paper_ledger(
        args.preregistration,
        args.observations,
        args.snapshot,
    )
    if (
        ledger.spec.primary_symbol != "0050"
        or ledger.spec.defensive_symbol != "00719B"
    ):
        raise ValueError(
            "authenticated paper ledger is not the 0050/00719B candidate"
        )
    last_observed_on = ledger.observations[-1].observed_on
    if last_observed_on >= args.expected_date:
        raise ValueError(
            "expected_date must be after the authenticated paper ledger"
        )
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
    official_ready = all(
        value.observed_on == args.expected_date
        for value in official_closes.values()
    )
    export_closes = None
    exports = None
    sequence_blocker = None
    if args.primary_export:
        primary_bars = load_mitake_daily_export(
            args.primary_export,
            expected_symbol="0050",
        )
        defensive_bars = load_mitake_daily_export(
            args.defensive_export,
            expected_symbol="00719B",
        )
        primary_export = primary_bars[-1]
        defensive_export = defensive_bars[-1]
        try:
            single_common_bar_after(
                primary_bars,
                defensive_bars,
                after=last_observed_on,
                expected_date=args.expected_date,
            )
        except ValueError as exc:
            sequence_blocker = str(exc)
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
    if sequence_blocker is not None:
        blockers += (sequence_blocker,)
    report = {
        "mode": "paper_only_no_broker",
        "expected_date": args.expected_date.isoformat(),
        "official_ready": official_ready,
        "ready": not blockers,
        "blockers": list(blockers),
        "ledger": {
            "last_observed_on": last_observed_on.isoformat(),
            "observation_count": len(ledger.observations),
            "ledger_hash": ledger.snapshot().ledger_hash,
            "snapshot_verified": True,
        },
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
