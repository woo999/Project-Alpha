"""Guarded single-day paper updates using only saved official evidence."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path

from project_alpha.action_schedule import verify_official_action_day
from project_alpha.daily_action_evidence import load_daily_action_evidence
from project_alpha.daily_official_close_evidence import (
    load_daily_official_close_evidence,
)
from project_alpha.paper_audit import file_evidence
from project_alpha.paper_daily import (
    PaperAction,
    load_paper_actions,
    validate_action_freshness,
)
from project_alpha.paper_tracking import PaperLedger
from project_alpha.paper_update import append_mark_to_market


def append_official_daily_mark(
    ledger: PaperLedger,
    *,
    close_evidence_dir: str | Path,
    action_evidence_dir: str | Path,
    primary_actions_path: str | Path,
    defensive_actions_path: str | Path,
) -> dict[str, object]:
    """Verify both evidence packages and append exactly one paper-only mark."""
    if not ledger.observations:
        raise ValueError("authenticated paper ledger has no initial observation")
    if (
        ledger.spec.primary_symbol != "0050"
        or ledger.spec.defensive_symbol != "00719B"
    ):
        raise ValueError("official-only updater supports only the 0050/00719B candidate")

    prior_hash = ledger.ledger_hash
    count_before = len(ledger.observations)
    previous_date = ledger.observations[-1].observed_on
    close_package = load_daily_official_close_evidence(close_evidence_dir)
    action_package = load_daily_action_evidence(
        action_evidence_dir,
        primary_action_path=primary_actions_path,
        defensive_action_path=defensive_actions_path,
    )
    target_date = close_package.observed_on
    if target_date <= previous_date:
        raise ValueError("official evidence date must be after the paper ledger")
    if action_package.verified_through != target_date:
        raise ValueError("close and corporate-action evidence dates do not match")
    if ledger.spec.is_rebalance_observation(count_before + 1):
        raise ValueError("scheduled rebalance requires an explicit paper allocation")

    primary_actions = load_paper_actions(primary_actions_path)
    defensive_actions = load_paper_actions(defensive_actions_path)
    validate_action_freshness(
        primary_actions,
        verified_through=action_package.verified_through,
        required_through=target_date,
        label="0050",
    )
    validate_action_freshness(
        defensive_actions,
        verified_through=action_package.verified_through,
        required_through=target_date,
        label="00719B",
    )
    verify_official_action_day(
        action_package.primary_source_path,
        source_url=action_package.primary_verification.source_url,
        symbol="0050",
        event_date=target_date,
        actions=primary_actions,
    )
    verify_official_action_day(
        action_package.defensive_source_path,
        source_url=action_package.defensive_verification.source_url,
        symbol="00719B",
        event_date=target_date,
        actions=defensive_actions,
    )
    primary_action = primary_actions.get(target_date, PaperAction(1.0, 0.0))
    defensive_action = defensive_actions.get(target_date, PaperAction(1.0, 0.0))
    if primary_action.split_ratio != 1.0 or defensive_action.split_ratio != 1.0:
        raise ValueError("split requires an explicit unit adjustment")

    append_mark_to_market(
        ledger,
        observed_on=target_date,
        primary_close=close_package.primary.close,
        defensive_close=close_package.defensive.close,
        primary_cash_dividend=primary_action.cash_dividend,
        defensive_cash_dividend=defensive_action.cash_dividend,
    )
    evidence_paths = {
        "close_manifest": close_package.manifest_path,
        "primary_close_source": close_package.primary_source_path,
        "defensive_close_source": close_package.defensive_source_path,
        "action_manifest": Path(action_evidence_dir) / "manifest.json",
        "primary_action_source": action_package.primary_source_path,
        "defensive_action_source": action_package.defensive_source_path,
        "primary_action_verification": action_package.primary_verification_path,
        "defensive_action_verification": action_package.defensive_verification_path,
        "primary_actions": Path(primary_actions_path),
        "defensive_actions": Path(defensive_actions_path),
    }
    return {
        "format_version": "official-paper-update-audit-v1",
        "mode": "paper_only_no_broker",
        "candidate_id": ledger.spec.candidate_id,
        "observed_on": target_date.isoformat(),
        "observation_count_before": count_before,
        "observation_count_after": len(ledger.observations),
        "prior_ledger_hash": prior_hash,
        "new_ledger_hash": ledger.ledger_hash,
        "inputs": {
            label: asdict(file_evidence(path))
            for label, path in evidence_paths.items()
        },
        "safety": {
            "broker_connected": False,
            "orders_placed": False,
            "real_capital_deployed": 0,
        },
    }
