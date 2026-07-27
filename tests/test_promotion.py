import pytest

from project_alpha.evaluation import GateDecision
from project_alpha.promotion import (
    DataProvenance,
    evaluate_promotion_readiness,
)


def test_split_adjusted_data_can_research_but_cannot_promote():
    decision = evaluate_promotion_readiness(
        GateDecision(passed=True, reasons=()),
        DataProvenance(
            source_name="user_file",
            symbol="0050",
            price_basis="split_adjusted",
        ),
    )

    assert not decision.passed
    assert "dividend-adjusted" in decision.reasons[0]


def test_total_return_data_and_passing_strategy_can_promote_to_paper_candidate():
    decision = evaluate_promotion_readiness(
        GateDecision(passed=True, reasons=()),
        DataProvenance(
            source_name="official_total_return_index",
            symbol="TW50TRI",
            price_basis="total_return",
        ),
    )

    assert decision.passed


def test_failed_strategy_cannot_promote_even_with_total_return_data():
    decision = evaluate_promotion_readiness(
        GateDecision(passed=False, reasons=("max_drawdown failed",)),
        DataProvenance(
            source_name="official_total_return_index",
            symbol="TW50TRI",
            price_basis="total_return",
        ),
    )

    assert not decision.passed
    assert decision.reasons == ("strategy: max_drawdown failed",)


@pytest.mark.parametrize("price_basis", ["adjusted", "", "TOTAL_RETURN"])
def test_unknown_price_basis_is_rejected(price_basis):
    with pytest.raises(ValueError, match="price_basis"):
        DataProvenance(
            source_name="source",
            symbol="0050",
            price_basis=price_basis,
        ).validate()
