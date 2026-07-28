from datetime import date

import pytest

import project_alpha.paper_snapshot_io as snapshot_io
from project_alpha.paper_tracking import CandidateSpec, PaperLedger, PaperObservation


def ledger():
    result = PaperLedger(
        CandidateSpec(
            candidate_id="candidate",
            declared_on=date(2026, 7, 28),
            historical_cutoff=date(2026, 7, 27),
            primary_symbol="0050",
            defensive_symbol="00719B",
            primary_weight=0.6,
            defensive_weight=0.4,
            rebalance_interval_trading_days=63,
        )
    )
    result.append(
        PaperObservation(
            observed_on=date(2026, 7, 28),
            portfolio_value=99.6,
            primary_close=1.0,
            defensive_close=1.0,
            primary_units=60,
            defensive_units=39,
            cash_balance=0.6,
            turnover_today=99.0,
            charged_transaction_costs_today=0.396,
        )
    )
    return result


def test_checkpoint_writes_matching_pair(tmp_path):
    observations = tmp_path / "observations.csv"
    snapshot = tmp_path / "snapshot.json"
    audit = tmp_path / "audit.json"
    target = ledger()
    snapshot_io.write_checkpoint(
        target,
        observations,
        snapshot,
        additional_text_files={audit: '{"audit":true}\n'},
    )
    loaded = snapshot_io.load_paper_ledger(
        _write_preregistration(tmp_path), observations
    )
    loaded.verify_snapshot(snapshot_io.load_snapshot(snapshot))
    assert audit.read_text(encoding="utf-8") == '{"audit":true}\n'


def test_checkpoint_rolls_back_if_second_replace_fails(tmp_path, monkeypatch):
    observations = tmp_path / "observations.csv"
    snapshot = tmp_path / "snapshot.json"
    observations.write_text("old observations\n", encoding="utf-8")
    snapshot.write_text("old snapshot\n", encoding="utf-8")
    original_replace = snapshot_io._replace_file
    calls = 0

    def fail_second(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated snapshot failure")
        original_replace(source, destination)

    monkeypatch.setattr(snapshot_io, "_replace_file", fail_second)
    with pytest.raises(OSError, match="simulated"):
        snapshot_io.write_checkpoint(ledger(), observations, snapshot)
    assert observations.read_text(encoding="utf-8") == "old observations\n"
    assert snapshot.read_text(encoding="utf-8") == "old snapshot\n"


def _write_preregistration(tmp_path):
    path = tmp_path / "preregistration.json"
    path.write_text(
        """{
  "candidate_id":"candidate",
  "declared_on":"2026-07-28",
  "historical_cutoff":"2026-07-27",
  "assets":{"primary":"0050","defensive":"00719B"},
  "weights":{"0050":0.6,"00719B":0.4},
  "rebalance_interval_trading_days":63,
  "rebalance_anchor":"first_forward_observation",
  "rebalance_weight_tolerance":0.01,
  "minimum_transaction_cost_rate":0.004,
  "maximum_forward_drawdown":0.2,
  "minimum_forward_observations":252,
  "paper_tracking_started":true,
  "current_state":"PAPER_TRACKING_ACTIVE",
  "live_ready":false,
  "leverage":false
}""",
        encoding="utf-8",
    )
    return path
