"""Fail-closed promotion gate separating research from paper readiness."""

from __future__ import annotations

from dataclasses import dataclass

from project_alpha.evaluation import GateDecision


VALID_PRICE_BASES = frozenset({"raw", "split_adjusted", "total_return"})


@dataclass(frozen=True)
class DataProvenance:
    source_name: str
    symbol: str
    price_basis: str

    def validate(self) -> None:
        if not self.source_name.strip():
            raise ValueError("source_name cannot be empty")
        if not self.symbol.strip():
            raise ValueError("symbol cannot be empty")
        if self.price_basis not in VALID_PRICE_BASES:
            raise ValueError(
                f"price_basis must be one of {sorted(VALID_PRICE_BASES)}"
            )


def evaluate_promotion_readiness(
    strategy_decision: GateDecision,
    provenance: DataProvenance,
) -> GateDecision:
    """Require a passing strategy and distribution-adjusted market data."""
    provenance.validate()
    reasons = [
        f"strategy: {reason}" for reason in strategy_decision.reasons
    ]
    if provenance.price_basis != "total_return":
        reasons.append(
            "data: total-return or dividend-adjusted prices are required; "
            f"received {provenance.price_basis}"
        )
    return GateDecision(passed=not reasons, reasons=tuple(reasons))
