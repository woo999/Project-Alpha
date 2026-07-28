"""Strict file I/O for offline paper-ledger checkpoints.

This module reads local files only.  It has no broker, order-entry, or network
capability.
"""

from __future__ import annotations

from dataclasses import asdict
import csv
from datetime import date
import io
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Iterable

from project_alpha.paper_tracking import (
    CandidateSpec,
    PaperLedger,
    PaperDecision,
    PaperObservation,
    PaperSnapshot,
)


OBSERVATION_COLUMNS = (
    "observed_on",
    "portfolio_value",
    "primary_close",
    "defensive_close",
    "primary_units",
    "defensive_units",
    "cash_balance",
    "turnover_today",
    "charged_transaction_costs_today",
)


def load_preregistered_candidate(path: Path) -> CandidateSpec:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("paper_tracking_started") is not True:
        raise ValueError("preregistration does not authorize paper tracking")
    if document.get("current_state") != "PAPER_TRACKING_ACTIVE":
        raise ValueError("preregistration state is not PAPER_TRACKING_ACTIVE")
    if document.get("live_ready") is not False:
        raise ValueError("paper snapshot input must explicitly remain not live-ready")
    if document.get("leverage") is not False:
        raise ValueError("paper candidate must explicitly prohibit leverage")

    assets = document["assets"]
    weights = document["weights"]
    primary = str(assets["primary"])
    defensive = str(assets["defensive"])
    return CandidateSpec(
        candidate_id=str(document["candidate_id"]),
        declared_on=date.fromisoformat(document["declared_on"]),
        historical_cutoff=date.fromisoformat(document["historical_cutoff"]),
        primary_symbol=primary,
        defensive_symbol=defensive,
        primary_weight=float(weights[primary]),
        defensive_weight=float(weights[defensive]),
        rebalance_interval_trading_days=int(
            document["rebalance_interval_trading_days"]
        ),
        rebalance_anchor=str(document["rebalance_anchor"]),
        rebalance_weight_tolerance=float(
            document["rebalance_weight_tolerance"]
        ),
        minimum_transaction_cost_rate=float(
            document["minimum_transaction_cost_rate"]
        ),
        maximum_drawdown=float(document["maximum_forward_drawdown"]),
        minimum_forward_observations=int(
            document["minimum_forward_observations"]
        ),
    )


def load_observations(path: Path) -> list[PaperObservation]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("paper observation CSV is empty")
        if tuple(reader.fieldnames) != OBSERVATION_COLUMNS:
            raise ValueError(
                "paper observation CSV columns must exactly match the frozen schema"
            )
        observations = []
        for row_number, row in enumerate(reader, start=2):
            try:
                observations.append(
                    PaperObservation(
                        observed_on=date.fromisoformat(row["observed_on"]),
                        portfolio_value=float(row["portfolio_value"]),
                        primary_close=float(row["primary_close"]),
                        defensive_close=float(row["defensive_close"]),
                        primary_units=int(row["primary_units"]),
                        defensive_units=int(row["defensive_units"]),
                        cash_balance=float(row["cash_balance"]),
                        turnover_today=float(row["turnover_today"]),
                        charged_transaction_costs_today=float(
                            row["charged_transaction_costs_today"]
                        ),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"invalid paper observation at CSV row {row_number}: {exc}"
                ) from exc
    if not observations:
        raise ValueError("paper observation CSV must contain at least one record")
    return observations


def build_snapshot(
    preregistration_path: Path,
    observations_path: Path,
) -> PaperSnapshot:
    return load_paper_ledger(
        preregistration_path,
        observations_path,
    ).snapshot()


def load_paper_ledger(
    preregistration_path: Path,
    observations_path: Path,
) -> PaperLedger:
    """Load and fully validate an active paper ledger from local files."""
    ledger = PaperLedger(load_preregistered_candidate(preregistration_path))
    ledger.extend(load_observations(observations_path))
    return ledger


def load_snapshot(path: Path) -> PaperSnapshot:
    """Strictly load a published checkpoint for pre-update verification."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("paper snapshot is missing or invalid JSON") from exc
    expected = {
        "format_version",
        "candidate_fingerprint",
        "observation_count",
        "last_observed_on",
        "ledger_hash",
        "decision",
    }
    if set(document) != expected:
        raise ValueError("paper snapshot fields do not match the frozen schema")
    decision_document = document["decision"]
    decision_fields = {
        "passed",
        "eligible",
        "observation_count",
        "cumulative_return",
        "maximum_drawdown",
        "reasons",
    }
    if not isinstance(decision_document, dict) or set(decision_document) != decision_fields:
        raise ValueError("paper snapshot decision fields do not match schema")

    def parse_count(value: object, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{label} must be a non-negative integer")
        return value

    def parse_optional_float(value: object, label: str) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{label} must be finite or null")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"{label} must be finite or null")
        return result

    for label in ("passed", "eligible"):
        if not isinstance(decision_document[label], bool):
            raise ValueError(f"snapshot decision {label} must be boolean")
    reasons = decision_document["reasons"]
    if not isinstance(reasons, list) or not all(
        isinstance(value, str) and value for value in reasons
    ):
        raise ValueError("snapshot decision reasons must be non-empty strings")
    last_observed_on = document["last_observed_on"]
    if last_observed_on is not None:
        try:
            last_observed_on = date.fromisoformat(last_observed_on)
        except (TypeError, ValueError) as exc:
            raise ValueError("snapshot last_observed_on is invalid") from exc
    for label in ("candidate_fingerprint", "ledger_hash"):
        value = document[label]
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError(f"snapshot {label} must be a SHA-256 hex digest")
    return PaperSnapshot(
        format_version=str(document["format_version"]),
        candidate_fingerprint=document["candidate_fingerprint"],
        observation_count=parse_count(
            document["observation_count"], "snapshot observation_count"
        ),
        last_observed_on=last_observed_on,
        ledger_hash=document["ledger_hash"],
        decision=PaperDecision(
            passed=decision_document["passed"],
            eligible=decision_document["eligible"],
            observation_count=parse_count(
                decision_document["observation_count"],
                "snapshot decision observation_count",
            ),
            cumulative_return=parse_optional_float(
                decision_document["cumulative_return"],
                "snapshot decision cumulative_return",
            ),
            maximum_drawdown=parse_optional_float(
                decision_document["maximum_drawdown"],
                "snapshot decision maximum_drawdown",
            ),
            reasons=tuple(reasons),
        ),
    )


def write_observations(
    observations: Iterable[PaperObservation],
    output_path: Path,
) -> None:
    """Atomically replace a fully validated paper observation CSV."""
    _atomic_write_text(output_path, _serialize_observations(observations), newline="")


def write_snapshot(snapshot: PaperSnapshot, output_path: Path) -> None:
    """Atomically replace a local checkpoint after full validation."""
    _atomic_write_text(output_path, snapshot.to_json() + "\n", newline="\n")


def write_checkpoint(
    ledger: PaperLedger,
    observations_path: Path,
    snapshot_path: Path,
) -> None:
    """Commit a ledger and its matching snapshot with runtime-error rollback.

    Both complete files are staged and fsynced before either published file is
    replaced.  If the second replacement raises, the first file is restored to
    its exact previous contents.  This protects against ordinary I/O failures;
    the snapshot guard still detects an abrupt process or machine failure.
    """
    observation_text = _serialize_observations(ledger.observations)
    snapshot_text = ledger.snapshot().to_json() + "\n"
    old_observations = (
        observations_path.read_text(encoding="utf-8")
        if observations_path.exists()
        else None
    )
    old_snapshot = (
        snapshot_path.read_text(encoding="utf-8")
        if snapshot_path.exists()
        else None
    )
    observation_stage = _stage_text(
        observations_path, observation_text, newline=""
    )
    snapshot_stage = _stage_text(snapshot_path, snapshot_text, newline="\n")
    observation_replaced = False
    snapshot_replaced = False
    try:
        _replace_file(observation_stage, observations_path)
        observation_replaced = True
        _replace_file(snapshot_stage, snapshot_path)
        snapshot_replaced = True
    except BaseException:
        if observation_replaced:
            _restore_text(observations_path, old_observations, newline="")
        if snapshot_replaced:
            _restore_text(snapshot_path, old_snapshot, newline="\n")
        raise
    finally:
        observation_stage.unlink(missing_ok=True)
        snapshot_stage.unlink(missing_ok=True)


def _serialize_observations(
    observations: Iterable[PaperObservation],
) -> str:
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=OBSERVATION_COLUMNS)
    writer.writeheader()
    for observation in observations:
        writer.writerow(asdict(observation))
    return handle.getvalue()


def _stage_text(output_path: Path, content: str, *, newline: str) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(
            descriptor, "w", encoding="utf-8", newline=newline
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        return temporary_path
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _replace_file(source: Path, destination: Path) -> None:
    source.replace(destination)


def _atomic_write_text(
    output_path: Path,
    content: str,
    *,
    newline: str,
) -> None:
    temporary_path = _stage_text(output_path, content, newline=newline)
    try:
        _replace_file(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _restore_text(
    output_path: Path,
    previous_content: str | None,
    *,
    newline: str,
) -> None:
    if previous_content is None:
        output_path.unlink(missing_ok=True)
    else:
        _atomic_write_text(output_path, previous_content, newline=newline)
