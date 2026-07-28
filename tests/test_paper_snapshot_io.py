from datetime import date
import json

import pytest

from project_alpha.paper_snapshot_io import (
    OBSERVATION_COLUMNS,
    build_snapshot,
    load_paper_ledger,
    load_preregistered_candidate,
)


def preregistration(active=True):
    return {
        "candidate_id": "0050-00719B-60-40-Q",
        "declared_on": "2026-07-28",
        "historical_cutoff": "2026-07-27",
        "assets": {"primary": "0050", "defensive": "00719B"},
        "weights": {"0050": 0.6, "00719B": 0.4},
        "rebalance_interval_trading_days": 63,
        "rebalance_anchor": "first_forward_observation",
        "rebalance_weight_tolerance": 0.01,
        "minimum_transaction_cost_rate": 0.004,
        "minimum_forward_observations": 252,
        "maximum_forward_drawdown": 0.2,
        "leverage": False,
        "paper_tracking_started": active,
        "current_state": (
            "PAPER_TRACKING_ACTIVE"
            if active
            else "BLOCKED_PENDING_PRIMARY_SOURCE_DIVIDEND_VERIFICATION"
        ),
        "live_ready": False,
    }


def write_preregistration(tmp_path, active=True):
    path = tmp_path / "preregistration.json"
    path.write_text(
        json.dumps(preregistration(active)),
        encoding="utf-8",
    )
    return path


def write_observations(tmp_path):
    path = tmp_path / "observations.csv"
    path.write_text(
        ",".join(OBSERVATION_COLUMNS)
        + "\n2026-07-28,100,1,1,60,40,0,100,0.4\n"
        + "2026-07-29,101,1.01,1.01,60,40,0,0,0\n",
        encoding="utf-8",
    )
    return path


def test_blocked_candidate_cannot_create_official_paper_snapshot(tmp_path):
    path = write_preregistration(tmp_path, active=False)
    with pytest.raises(ValueError, match="does not authorize"):
        load_preregistered_candidate(path)


def test_active_candidate_creates_deterministic_snapshot(tmp_path):
    prereg = write_preregistration(tmp_path)
    observations = write_observations(tmp_path)
    first = build_snapshot(prereg, observations)
    second = build_snapshot(prereg, observations)
    assert first == second
    assert first.observation_count == 2
    assert first.last_observed_on == date(2026, 7, 29)
    assert len(first.ledger_hash) == 64
    assert first.decision.eligible is False


def test_load_paper_ledger_returns_validated_records(tmp_path):
    ledger = load_paper_ledger(
        write_preregistration(tmp_path),
        write_observations(tmp_path),
    )
    assert len(ledger.observations) == 2
    assert ledger.observations[-1].observed_on == date(2026, 7, 29)


def test_csv_schema_and_rows_are_strict(tmp_path):
    prereg = write_preregistration(tmp_path)
    bad_schema = tmp_path / "bad_schema.csv"
    bad_schema.write_text("observed_on,portfolio_value\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly match"):
        build_snapshot(prereg, bad_schema)

    bad_row = tmp_path / "bad_row.csv"
    bad_row.write_text(
        ",".join(OBSERVATION_COLUMNS)
        + "\n2026-07-28,100,1,1,60.5,39.5,0,100,0.4\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="CSV row 2"):
        build_snapshot(prereg, bad_row)
