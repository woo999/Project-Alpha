"""Discover and safely advance one official paper-tracking day."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError

from project_alpha.next_official_bundle import OfficialDatesNotSynchronized
from project_alpha.official_paper_advance import advance_next_official_paper
from project_alpha.paper_snapshot_io import load_authenticated_paper_ledger
from project_alpha.paper_tracking import PaperLedger


def run_advance(
    args: argparse.Namespace,
    ledger: PaperLedger,
    *,
    advance: Callable[..., dict[str, object]] = advance_next_official_paper,
) -> tuple[dict[str, object], int]:
    """Classify source unavailability separately from local checkpoint failure."""
    last_observed_on = ledger.observations[-1].observed_on.isoformat()
    try:
        return (
            advance(
                ledger,
                observations_path=args.observations,
                snapshot_path=args.snapshot,
                primary_actions_path=args.primary_actions,
                defensive_actions_path=args.defensive_actions,
                bundle_root=args.bundle_root,
                audit_dir=args.audit_dir,
                evidence_dir=args.evidence_dir,
                write=args.write,
            ),
            0,
        )
    except OfficialDatesNotSynchronized as exc:
        return (
            {
                "mode": "paper_only_no_broker",
                "ready": False,
                "advanced": False,
                "write_requested": args.write,
                "reason": "official close sources are not synchronized",
                "official_dates": {
                    "0050": exc.primary_date,
                    "00719B": exc.defensive_date,
                },
                "last_observed_on": last_observed_on,
            },
            0,
        )
    except (HTTPError, URLError, TimeoutError) as exc:
        error = (
            f"HTTP {exc.code}" if isinstance(exc, HTTPError) else type(exc).__name__
        )
        return (
            {
                "mode": "paper_only_no_broker",
                "ready": False,
                "advanced": False,
                "write_requested": args.write,
                "reason": "official source unavailable",
                "source_error": {
                    "error": error,
                    "url": getattr(exc, "url", None),
                },
                "last_observed_on": last_observed_on,
            },
            0,
        )
    except OSError as exc:
        return (
            {
                "mode": "paper_only_no_broker",
                "ready": False,
                "advanced": False,
                "write_requested": args.write,
                "reason": "local paper checkpoint failure",
                "local_error": {
                    "error": type(exc).__name__,
                    "message": str(exc),
                },
                "last_observed_on": last_observed_on,
            },
            1,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Discover, verify, and optionally commit the next official paper day."
        )
    )
    parser.add_argument("preregistration", type=Path)
    parser.add_argument("observations", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("primary_actions", type=Path)
    parser.add_argument("defensive_actions", type=Path)
    parser.add_argument("bundle_root", type=Path)
    parser.add_argument("audit_dir", type=Path)
    parser.add_argument("evidence_dir", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    ledger = load_authenticated_paper_ledger(
        args.preregistration, args.observations, args.snapshot
    )
    result, exit_code = run_advance(args, ledger)
    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
