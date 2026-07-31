"""One guarded operation for discovering and advancing official paper data."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from project_alpha.next_official_bundle import prepare_next_official_paper_bundle
from project_alpha.official_evidence_summary import (
    build_official_evidence_summary,
)
from project_alpha.official_paper_bundle import load_official_paper_bundle
from project_alpha.official_paper_update import append_official_bundle_mark
from project_alpha.official_source import OfficialSourceDownload, fetch_official_source
from project_alpha.paper_snapshot_io import write_checkpoint
from project_alpha.paper_tracking import PaperLedger


def advance_next_official_paper(
    ledger: PaperLedger,
    *,
    observations_path: str | Path,
    snapshot_path: str | Path,
    primary_actions_path: str | Path,
    defensive_actions_path: str | Path,
    bundle_root: str | Path,
    audit_dir: str | Path,
    evidence_dir: str | Path,
    write: bool = False,
    fetcher: Callable[[str], OfficialSourceDownload] = fetch_official_source,
) -> dict[str, object]:
    """Discover, verify, and optionally commit exactly one official paper day."""
    if not ledger.observations:
        raise ValueError("authenticated paper ledger has no initial observation")
    output = prepare_next_official_paper_bundle(
        ledger,
        primary_action_path=primary_actions_path,
        defensive_action_path=defensive_actions_path,
        output_root=bundle_root,
        fetcher=fetcher,
    )
    if output is None:
        return {
            "mode": "paper_only_no_broker",
            "ready": False,
            "advanced": False,
            "write_requested": write,
            "reason": "official sources have no date after the authenticated ledger",
            "last_observed_on": ledger.observations[-1].observed_on.isoformat(),
            "observation_count": len(ledger.observations),
            "ledger_hash": ledger.ledger_hash,
        }

    bundle = load_official_paper_bundle(
        output,
        primary_action_path=primary_actions_path,
        defensive_action_path=defensive_actions_path,
    )
    observed_text = bundle.observed_on.isoformat()
    audit_path = Path(audit_dir) / f"{observed_text}.json"
    evidence_path = Path(evidence_dir) / f"{observed_text}.json"
    if audit_path == evidence_path:
        raise ValueError("audit and evidence summary outputs must be different")
    if write:
        for path in (audit_path, evidence_path):
            if path.exists():
                raise ValueError(
                    f"checkpoint evidence already exists; refusing to overwrite: {path}"
                )

    audit = append_official_bundle_mark(
        ledger,
        bundle_dir=output,
        primary_actions_path=primary_actions_path,
        defensive_actions_path=defensive_actions_path,
    )
    summary = build_official_evidence_summary(
        bundle_dir=output,
        audit=audit,
        primary_actions_path=primary_actions_path,
        defensive_actions_path=defensive_actions_path,
    )
    if write:
        write_checkpoint(
            ledger,
            Path(observations_path),
            Path(snapshot_path),
            additional_text_files={
                audit_path: json.dumps(audit, indent=2, sort_keys=True) + "\n",
                evidence_path: json.dumps(summary, indent=2, sort_keys=True) + "\n",
            },
        )

    return {
        "mode": "paper_only_no_broker",
        "ready": True,
        "advanced": write,
        "write_requested": write,
        "observed_on": observed_text,
        "closes": {
            "0050": bundle.close.primary.close,
            "00719B": bundle.close.defensive.close,
        },
        "bundle_dir": str(output),
        "audit_output": str(audit_path),
        "evidence_summary_output": str(evidence_path),
        "observation_count": len(ledger.observations),
        "ledger_hash": ledger.ledger_hash,
        "safety": audit["safety"],
    }
