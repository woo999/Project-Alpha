"""Build a deterministic public summary from a verified official bundle."""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from project_alpha.official_close import official_close_for_symbol
from project_alpha.official_paper_bundle import load_official_paper_bundle
from project_alpha.paper_daily import load_paper_actions


def _audit_input(
    audit: dict[str, object],
    label: str,
) -> dict[str, object]:
    inputs = audit.get("inputs")
    if not isinstance(inputs, dict) or not isinstance(inputs.get(label), dict):
        raise ValueError(f"official audit input is missing: {label}")
    evidence = inputs[label]
    byte_count = evidence.get("byte_count")
    sha256 = evidence.get("sha256")
    if (
        isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count < 1
        or not isinstance(sha256, str)
        or len(sha256) != 64
        or any(character not in "0123456789abcdef" for character in sha256)
    ):
        raise ValueError(f"official audit input is malformed: {label}")
    return evidence


def _replayable_close_row(
    source_path: Path,
    *,
    source_url: str,
    symbol: str,
    expected_date: date,
    expected_close: float,
) -> dict[str, object]:
    """Extract the exact official row needed to replay one close."""
    rows = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("official close source must be a JSON array")
    hostname = (urlparse(source_url).hostname or "").lower()
    if hostname == "openapi.twse.com.tw":
        symbol_key = "Code"
    elif hostname == "www.tpex.org.tw":
        symbol_key = "SecuritiesCompanyCode"
    else:
        raise ValueError("unsupported official close source")
    matches = [
        row
        for row in rows
        if isinstance(row, dict) and str(row.get(symbol_key, "")).strip() == symbol
    ]
    if len(matches) != 1:
        raise ValueError("official close replay row must be unique")
    row = matches[0]
    replayed = official_close_for_symbol(
        json.dumps([row], ensure_ascii=False).encode("utf-8"),
        source_url=source_url,
        symbol=symbol,
    )
    if replayed.observed_on != expected_date or not math.isclose(
        replayed.close, expected_close, rel_tol=0, abs_tol=1e-9
    ):
        raise ValueError("official close replay row does not match verified close")
    return row


def build_official_evidence_summary(
    *,
    bundle_dir: str | Path,
    audit: dict[str, object],
    primary_actions_path: str | Path,
    defensive_actions_path: str | Path,
) -> dict[str, object]:
    """Build the evidence summary only after reloading the complete bundle."""
    bundle = load_official_paper_bundle(
        bundle_dir,
        primary_action_path=primary_actions_path,
        defensive_action_path=defensive_actions_path,
    )
    observed_on = bundle.observed_on
    observed_text = observed_on.isoformat()
    if (
        audit.get("mode") != "paper_only_no_broker"
        or audit.get("observed_on") != observed_text
    ):
        raise ValueError("official audit does not match the evidence bundle")
    safety = audit.get("safety")
    expected_safety = {
        "broker_connected": False,
        "orders_placed": False,
        "real_capital_deployed": 0,
    }
    if safety != expected_safety:
        raise ValueError("official audit paper-safety declaration changed")
    ledger_hash = audit.get("new_ledger_hash")
    if (
        not isinstance(ledger_hash, str)
        or len(ledger_hash) != 64
        or any(character not in "0123456789abcdef" for character in ledger_hash)
    ):
        raise ValueError("official audit ledger hash is invalid")
    manifest = audit.get("official_bundle_manifest")
    if not isinstance(manifest, dict):
        raise ValueError("official audit bundle manifest is missing")
    bundle_hash = manifest.get("sha256")
    if (
        not isinstance(bundle_hash, str)
        or len(bundle_hash) != 64
        or any(character not in "0123456789abcdef" for character in bundle_hash)
    ):
        raise ValueError("official audit bundle manifest hash is invalid")

    close_manifest = json.loads(
        bundle.close.manifest_path.read_text(encoding="utf-8")
    )
    close_sources = close_manifest["sources"]
    primary_actions = load_paper_actions(primary_actions_path)
    defensive_actions = load_paper_actions(defensive_actions_path)

    primary_close_source = _audit_input(audit, "primary_close_source")
    defensive_close_source = _audit_input(audit, "defensive_close_source")
    primary_action_source = _audit_input(audit, "primary_action_source")
    defensive_action_source = _audit_input(audit, "defensive_action_source")
    primary_close_url = close_sources["0050"]["url"]
    defensive_close_url = close_sources["00719B"]["url"]

    return {
        "format_version": "official-evidence-summary-v2",
        "mode": "paper_only_no_broker",
        "observed_on": observed_text,
        "closes": {
            "0050": {
                "close": bundle.close.primary.close,
                "source_url": primary_close_url,
                "source_row": _replayable_close_row(
                    bundle.close.primary_source_path,
                    source_url=primary_close_url,
                    symbol="0050",
                    expected_date=observed_on,
                    expected_close=bundle.close.primary.close,
                ),
                "raw_byte_count": primary_close_source["byte_count"],
                "raw_sha256": primary_close_source["sha256"],
            },
            "00719B": {
                "close": bundle.close.defensive.close,
                "source_url": defensive_close_url,
                "source_row": _replayable_close_row(
                    bundle.close.defensive_source_path,
                    source_url=defensive_close_url,
                    symbol="00719B",
                    expected_date=observed_on,
                    expected_close=bundle.close.defensive.close,
                ),
                "raw_byte_count": defensive_close_source["byte_count"],
                "raw_sha256": defensive_close_source["sha256"],
            },
        },
        "corporate_actions": {
            "0050": {
                "event_on_observed_date": observed_on in primary_actions,
                "source_url": bundle.actions.primary_verification.source_url,
                "raw_byte_count": primary_action_source["byte_count"],
                "raw_sha256": primary_action_source["sha256"],
            },
            "00719B": {
                "event_on_observed_date": observed_on in defensive_actions,
                "source_url": bundle.actions.defensive_verification.source_url,
                "raw_byte_count": defensive_action_source["byte_count"],
                "raw_sha256": defensive_action_source["sha256"],
            },
        },
        "bundle_manifest_sha256": bundle_hash,
        "new_ledger_hash": ledger_hash,
        "safety": expected_safety,
    }
