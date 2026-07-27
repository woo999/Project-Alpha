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


def observation(day, value):
    return PaperObservation(day, value, 100.0, 30.0)


def test_fingerprint_is_stable_and_changes_with_rule():
    assert candidate().fingerprint == candidate().fingerprint
    assert candidate(4).fingerprint != candidate(3).fingerprint


def test_historical_or_duplicate_observations_are_rejected():
    ledger = PaperLedger(candidate())
    with pytest.raises(ValueError, match="after historical cutoff"):
        ledger.append(observation(date(2026, 7, 27), 1.0))
    ledger.append(observation(date(2026, 7, 28), 1.0))
    with pytest.raises(ValueError, match="strictly chronological"):
        ledger.append(observation(date(2026, 7, 28), 1.01))


def test_candidate_cannot_pass_before_minimum_forward_history():
    ledger = PaperLedger(candidate())
    ledger.extend(
        [
            observation(date(2026, 7, 28), 1.0),
            observation(date(2026, 7, 29), 1.01),
        ]
    )
    assert ledger.evaluate().eligible is False
    assert ledger.evaluate().passed is False


def test_candidate_passes_only_after_forward_return_and_drawdown_gates():
    ledger = PaperLedger(candidate())
    start = date(2026, 7, 28)
    ledger.extend(
        observation(start + timedelta(days=offset), value)
        for offset, value in enumerate((1.0, 0.95, 1.05))
    )
    decision = ledger.evaluate()
    assert decision.eligible is True
    assert decision.passed is True
    assert decision.maximum_drawdown == pytest.approx(-0.05)
