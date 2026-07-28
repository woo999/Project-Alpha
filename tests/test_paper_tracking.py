from datetime import date, timedelta

import pytest

from project_alpha.paper_tracking import (
    CandidateSpec,
    PaperLedger,
    PaperObservation,
)


def candidate(minimum_forward_observations=3):
    return CandidateSpec(
        candidate_id="0050-00719B-60-40-Q",
        declared_on=date(2026, 7, 28),
        historical_cutoff=date(2026, 7, 27),
        primary_symbol="0050",
        defensive_symbol="00719B",
        primary_weight=0.60,
        defensive_weight=0.40,
        rebalance_interval_trading_days=63,
        minimum_forward_observations=minimum_forward_observations,
    )


def observation(day, value, turnover=0.0, costs=0.0):
    marked_price = value / 100
    return PaperObservation(
        day,
        value,
        marked_price,
        marked_price,
        60,
        40,
        0.0,
        turnover_today=turnover,
        charged_transaction_costs_today=costs,
    )


def initial_observation(day, value):
    return observation(day, value, turnover=100.0, costs=0.4)


def test_fingerprint_is_stable_and_changes_with_rule():
    assert candidate().fingerprint == candidate().fingerprint
    assert candidate(4).fingerprint != candidate(3).fingerprint


def test_rebalance_schedule_is_anchored_without_off_by_one_ambiguity():
    spec = candidate()
    assert spec.is_rebalance_observation(1) is True
    assert spec.is_rebalance_observation(63) is False
    assert spec.is_rebalance_observation(64) is True
    assert spec.is_rebalance_observation(126) is False
    assert spec.is_rebalance_observation(127) is True
    with pytest.raises(ValueError, match="positive"):
        spec.is_rebalance_observation(0)


def test_observation_must_reconcile_positions_and_cash():
    with pytest.raises(ValueError, match="marked positions"):
        PaperObservation(date(2026, 7, 28), 101.0, 1.0, 1.0, 60, 40, 0.0)
    with pytest.raises(ValueError, match="non-negative"):
        PaperObservation(date(2026, 7, 28), 99.0, 1.0, 1.0, 60, 40, -1.0)


def test_rebalance_observation_must_match_frozen_weights():
    ledger = PaperLedger(candidate())
    off_target = PaperObservation(
        date(2026, 7, 28), 100.0, 1.0, 1.0, 70, 30, 0.0, 100.0, 0.4
    )
    with pytest.raises(ValueError, match="frozen target weights"):
        ledger.append(off_target)


def test_hidden_turnover_and_undercharged_costs_are_rejected():
    ledger = PaperLedger(candidate())
    ledger.append(initial_observation(date(2026, 7, 28), 100.0))
    hidden_trade = PaperObservation(
        date(2026, 7, 29), 100.0, 1.0, 1.0, 60, 40, 0.0, 1.0, 0.004
    )
    with pytest.raises(ValueError, match="forbidden"):
        ledger.append(hidden_trade)

    undercharged = PaperObservation(
        date(2026, 7, 28), 100.0, 1.0, 1.0, 60, 40, 0.0, 100.0, 0.39
    )
    with pytest.raises(ValueError, match="minimum rate"):
        PaperLedger(candidate()).append(undercharged)


def test_historical_or_duplicate_observations_are_rejected():
    ledger = PaperLedger(candidate())
    with pytest.raises(ValueError, match="after historical cutoff"):
        ledger.append(observation(date(2026, 7, 27), 1.0))
    ledger.append(initial_observation(date(2026, 7, 28), 1.0))
    with pytest.raises(ValueError, match="strictly chronological"):
        ledger.append(observation(date(2026, 7, 28), 1.01))


def test_candidate_cannot_pass_before_minimum_forward_history():
    ledger = PaperLedger(candidate())
    ledger.extend(
        [
            initial_observation(date(2026, 7, 28), 1.0),
            observation(date(2026, 7, 29), 1.01),
        ]
    )
    assert ledger.evaluate().eligible is False
    assert ledger.evaluate().passed is False


def test_candidate_passes_only_after_forward_return_and_drawdown_gates():
    ledger = PaperLedger(candidate())
    start = date(2026, 7, 28)
    ledger.append(initial_observation(start, 1.0))
    ledger.extend(
        observation(start + timedelta(days=offset), value)
        for offset, value in enumerate((0.95, 1.05), start=1)
    )
    decision = ledger.evaluate()
    assert decision.eligible is True
    assert decision.passed is True
    assert decision.maximum_drawdown == pytest.approx(-0.05)


def test_snapshot_is_stable_and_detects_record_tampering():
    start = date(2026, 7, 28)
    ledger = PaperLedger(candidate())
    ledger.extend(
        [
            initial_observation(start, 100.0),
            observation(start + timedelta(days=1), 101.0),
        ]
    )
    snapshot = ledger.snapshot()

    assert snapshot == ledger.snapshot()
    assert snapshot.observation_count == 2
    assert snapshot.last_observed_on == start + timedelta(days=1)
    assert snapshot.candidate_fingerprint == candidate().fingerprint
    assert len(snapshot.ledger_hash) == 64
    ledger.verify_snapshot(snapshot)

    changed = PaperLedger(candidate())
    changed.extend(
        [
            initial_observation(start, 100.0),
            observation(start + timedelta(days=1), 101.01),
        ]
    )
    assert changed.ledger_hash != snapshot.ledger_hash
    with pytest.raises(ValueError, match="does not match"):
        changed.verify_snapshot(snapshot)


def test_snapshot_becomes_stale_after_append_or_rule_change():
    start = date(2026, 7, 28)
    ledger = PaperLedger(candidate())
    ledger.append(initial_observation(start, 100.0))
    snapshot = ledger.snapshot()
    ledger.append(observation(start + timedelta(days=1), 101.0))
    with pytest.raises(ValueError, match="does not match"):
        ledger.verify_snapshot(snapshot)

    changed_rule = PaperLedger(candidate(minimum_forward_observations=4))
    changed_rule.append(initial_observation(start, 100.0))
    assert changed_rule.ledger_hash != snapshot.ledger_hash
