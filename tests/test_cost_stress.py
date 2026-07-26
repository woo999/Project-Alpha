import pandas as pd
import pytest

from project_alpha.cost_stress import (
    CostStressCriteria,
    evaluate_cost_stress,
)
from project_alpha.evaluation import AcceptanceCriteria


def test_higher_costs_can_reject_a_fragile_strategy():
    rows = 20
    result = pd.DataFrame(
        {
            "position": [1.0] * rows,
            "asset_return": [0.01] * rows,
            "turnover": [1.0] * rows,
            "cost": [0.006] * rows,
        }
    )
    criteria = AcceptanceCriteria(
        minimum_observations=2,
        minimum_total_return=0.0,
        minimum_sharpe=-100.0,
        minimum_calmar=-100.0,
        minimum_profit_factor=0.0,
        maximum_drawdown=0.50,
        minimum_trades=0.0,
    )

    report = evaluate_cost_stress(
        result,
        acceptance_criteria=criteria,
        stress_criteria=CostStressCriteria(multipliers=(1.0, 2.0)),
    )

    assert report.scenarios[0].decision.passed
    assert not report.scenarios[1].decision.passed
    assert not report.decision.passed
    assert any("2.0x costs" in reason for reason in report.decision.reasons)


def test_cost_stress_rejects_cost_reducing_scenarios():
    with pytest.raises(ValueError, match="cannot reduce"):
        CostStressCriteria(multipliers=(1.0, 0.5)).validate()
