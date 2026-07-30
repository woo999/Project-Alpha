"""Verify the persistent official-evidence chain behind a paper ledger."""

from __future__ import annotations

import json
import math
from pathlib import Path

from project_alpha.paper_tracking import PaperLedger


def _load_json(path: Path) -> dict[str, object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid evidence JSON: {path}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"evidence document must be an object: {path}")
    return document


def _require_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} does not match the paper ledger")


def _verify_source(
    summary_entry: object,
    audit_entry: object,
    *,
    label: str,
) -> None:
    if not isinstance(summary_entry, dict) or not isinstance(audit_entry, dict):
        raise ValueError(f"{label} source evidence is malformed")
    _require_equal(
        summary_entry.get("raw_byte_count"),
        audit_entry.get("byte_count"),
        f"{label} byte count",
    )
    _require_equal(
        summary_entry.get("raw_sha256"),
        audit_entry.get("sha256"),
        f"{label} SHA-256",
    )


def verify_paper_evidence_chain(
    ledger: PaperLedger,
    *,
    audit_dir: str | Path,
    evidence_dir: str | Path,
) -> dict[str, object]:
    """Verify every post-initial observation against its audit and summary."""
    if len(ledger.observations) < 1:
        raise ValueError("paper ledger has no initial observation")

    audit_root = Path(audit_dir)
    evidence_root = Path(evidence_dir)
    expected_dates = {
        observation.observed_on.isoformat()
        for observation in ledger.observations[1:]
    }
    audit_dates = {path.stem for path in audit_root.glob("*.json")}
    evidence_dates = {path.stem for path in evidence_root.glob("*.json")}
    _require_equal(audit_dates, expected_dates, "daily audit file set")
    _require_equal(evidence_dates, expected_dates, "official evidence file set")

    for observation_count in range(2, len(ledger.observations) + 1):
        observation = ledger.observations[observation_count - 1]
        observed_on = observation.observed_on.isoformat()
        audit = _load_json(audit_root / f"{observed_on}.json")
        summary = _load_json(evidence_root / f"{observed_on}.json")

        prior = PaperLedger(
            ledger.spec,
            list(ledger.observations[: observation_count - 1]),
        )
        current = PaperLedger(
            ledger.spec,
            list(ledger.observations[:observation_count]),
        )
        for document, label in ((audit, "audit"), (summary, "summary")):
            _require_equal(document.get("mode"), "paper_only_no_broker", f"{label} mode")
            _require_equal(document.get("observed_on"), observed_on, f"{label} date")
            safety = document.get("safety")
            if safety != {
                "broker_connected": False,
                "orders_placed": False,
                "real_capital_deployed": 0,
            }:
                raise ValueError(f"{label} paper-safety declaration changed")

        _require_equal(
            audit.get("observation_count_before"),
            observation_count - 1,
            "audit prior observation count",
        )
        _require_equal(
            audit.get("observation_count_after"),
            observation_count,
            "audit new observation count",
        )
        _require_equal(
            audit.get("prior_ledger_hash"),
            prior.ledger_hash,
            "audit prior ledger hash",
        )
        _require_equal(
            audit.get("new_ledger_hash"),
            current.ledger_hash,
            "audit new ledger hash",
        )
        _require_equal(
            summary.get("new_ledger_hash"),
            current.ledger_hash,
            "summary ledger hash",
        )

        manifest = audit.get("official_bundle_manifest")
        if not isinstance(manifest, dict):
            raise ValueError("audit official bundle manifest is malformed")
        _require_equal(
            summary.get("bundle_manifest_sha256"),
            manifest.get("sha256"),
            "summary bundle manifest hash",
        )

        closes = summary.get("closes")
        actions = summary.get("corporate_actions")
        inputs = audit.get("inputs")
        if (
            not isinstance(closes, dict)
            or not isinstance(actions, dict)
            or not isinstance(inputs, dict)
        ):
            raise ValueError("official evidence source maps are malformed")
        primary_close = closes.get("0050")
        defensive_close = closes.get("00719B")
        if not isinstance(primary_close, dict) or not isinstance(defensive_close, dict):
            raise ValueError("official close summary is malformed")
        if not math.isclose(
            float(primary_close.get("close", float("nan"))),
            observation.primary_close,
        ):
            raise ValueError("0050 summary close does not match the paper ledger")
        if not math.isclose(
            float(defensive_close.get("close", float("nan"))),
            observation.defensive_close,
        ):
            raise ValueError("00719B summary close does not match the paper ledger")

        _verify_source(
            primary_close,
            inputs.get("primary_close_source"),
            label="0050 close",
        )
        _verify_source(
            defensive_close,
            inputs.get("defensive_close_source"),
            label="00719B close",
        )
        _verify_source(
            actions.get("0050"),
            inputs.get("primary_action_source"),
            label="0050 corporate action",
        )
        _verify_source(
            actions.get("00719B"),
            inputs.get("defensive_action_source"),
            label="00719B corporate action",
        )
        for symbol in ("0050", "00719B"):
            entry = actions.get(symbol)
            if not isinstance(entry, dict) or entry.get("event_on_observed_date") is not False:
                raise ValueError(
                    f"{symbol} corporate-action status is not explicitly no-event"
                )

    return {
        "mode": "paper_only_no_broker",
        "observation_count": len(ledger.observations),
        "verified_official_days": len(expected_dates),
        "last_observed_on": ledger.observations[-1].observed_on.isoformat(),
        "ledger_hash": ledger.ledger_hash,
        "valid": True,
    }
