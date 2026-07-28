"""Deterministic source provenance for offline paper-ledger batches."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
from pathlib import Path

from project_alpha.mitake import MitakeDailyBar
from project_alpha.paper_daily import PaperAction


@dataclass(frozen=True)
class FileEvidence:
    file_name: str
    byte_count: int
    sha256: str


def file_evidence(path: str | Path) -> FileEvidence:
    source = Path(path)
    digest = hashlib.sha256()
    byte_count = 0
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            byte_count += len(chunk)
    return FileEvidence(source.name, byte_count, digest.hexdigest())


def build_batch_audit(
    *,
    candidate_id: str,
    prior_ledger_hash: str,
    new_ledger_hash: str,
    observation_count_before: int,
    observation_count_after: int,
    appended_dates: tuple[date, ...],
    primary_export_path: Path,
    defensive_export_path: Path,
    primary_actions_path: Path,
    defensive_actions_path: Path,
    primary_bars: tuple[MitakeDailyBar, ...],
    defensive_bars: tuple[MitakeDailyBar, ...],
    primary_actions: dict[date, PaperAction],
    defensive_actions: dict[date, PaperAction],
) -> dict[str, object]:
    """Build a stable audit document that can be committed with the ledger."""
    if observation_count_after - observation_count_before != len(appended_dates):
        raise ValueError("audit observation counts do not match appended dates")
    if not primary_bars or not defensive_bars:
        raise ValueError("audit requires non-empty market exports")

    def coverage(bars: tuple[MitakeDailyBar, ...]) -> dict[str, object]:
        return {
            "row_count": len(bars),
            "first_date": bars[0].observed_on.isoformat(),
            "last_date": bars[-1].observed_on.isoformat(),
        }

    def action_coverage(actions: dict[date, PaperAction]) -> dict[str, object]:
        dates = sorted(actions)
        return {
            "event_count": len(dates),
            "first_event_date": dates[0].isoformat(),
            "last_event_date": dates[-1].isoformat(),
        }

    return {
        "format_version": "paper-source-audit-v1",
        "candidate_id": candidate_id,
        "mode": "paper_only_no_broker",
        "observation_count_before": observation_count_before,
        "observation_count_after": observation_count_after,
        "appended_dates": [value.isoformat() for value in appended_dates],
        "prior_ledger_hash": prior_ledger_hash,
        "new_ledger_hash": new_ledger_hash,
        "inputs": {
            "primary_export": {
                **asdict(file_evidence(primary_export_path)),
                **coverage(primary_bars),
            },
            "defensive_export": {
                **asdict(file_evidence(defensive_export_path)),
                **coverage(defensive_bars),
            },
            "primary_actions": {
                **asdict(file_evidence(primary_actions_path)),
                **action_coverage(primary_actions),
            },
            "defensive_actions": {
                **asdict(file_evidence(defensive_actions_path)),
                **action_coverage(defensive_actions),
            },
        },
        "safety": {
            "broker_connected": False,
            "orders_placed": False,
            "real_capital_deployed": 0,
        },
    }
