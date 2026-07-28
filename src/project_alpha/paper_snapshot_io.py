"""Strict file I/O for offline paper-ledger checkpoints.

This module reads local files only.  It has no broker, order-entry, or network
capability.
"""

from __future__ import annotations

import csv
from datetime import date
import json
import os
from pathlib import Path
import tempfile

from project_alpha.paper_tracking import (
    CandidateSpec,
    PaperLedger,
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


def write_snapshot(snapshot: PaperSnapshot, output_path: Path) -> None:
    """Atomically replace a local checkpoint after full validation."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(snapshot.to_json())
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(output_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
