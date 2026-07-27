"""Fail-closed alignment and eligibility checks for multi-asset research."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from project_alpha.evaluation import GateDecision
from project_alpha.promotion import DataProvenance


@dataclass(frozen=True)
class MultiAssetCriteria:
    minimum_observations: int = 2000
    minimum_years: float = 8.0
    minimum_overlap_fraction: float = 0.98

    def validate(self) -> None:
        if self.minimum_observations < 252:
            raise ValueError("minimum_observations must be at least 252")
        if self.minimum_years <= 0.0:
            raise ValueError("minimum_years must be positive")
        if not 0.0 < self.minimum_overlap_fraction <= 1.0:
            raise ValueError("minimum_overlap_fraction must be in (0, 1]")


@dataclass(frozen=True)
class MultiAssetAlignment:
    prices: pd.DataFrame
    observations: int
    years: float
    overlap_fraction: float
    return_correlation: float
    decision: GateDecision


def _clean_series(prices: pd.Series, name: str) -> pd.Series:
    clean = pd.to_numeric(prices, errors="raise").astype(float)
    if clean.empty:
        raise ValueError(f"{name} prices cannot be empty")
    if clean.index.has_duplicates:
        raise ValueError(f"{name} prices contain duplicate dates")
    if not clean.index.is_monotonic_increasing:
        raise ValueError(f"{name} prices must be chronological")
    if clean.isna().any() or not clean.map(math.isfinite).all():
        raise ValueError(f"{name} prices must be finite and complete")
    if (clean <= 0.0).any():
        raise ValueError(f"{name} prices must be positive")
    clean.name = name
    return clean


def align_multi_asset_prices(
    primary: pd.Series,
    defensive: pd.Series,
    primary_provenance: DataProvenance,
    defensive_provenance: DataProvenance,
    criteria: MultiAssetCriteria | None = None,
) -> MultiAssetAlignment:
    """Align without forward filling and report every research blocker."""
    rules = criteria or MultiAssetCriteria()
    rules.validate()
    primary_provenance.validate()
    defensive_provenance.validate()
    clean_primary = _clean_series(primary, "primary")
    clean_defensive = _clean_series(defensive, "defensive")

    common_index = clean_primary.index.intersection(clean_defensive.index)
    aligned = pd.concat(
        [
            clean_primary.loc[common_index],
            clean_defensive.loc[common_index],
        ],
        axis=1,
    )
    observations = len(aligned)
    denominator = min(len(clean_primary), len(clean_defensive))
    overlap_fraction = observations / denominator if denominator else 0.0
    years = (
        (aligned.index[-1] - aligned.index[0]).days / 365.2425
        if observations >= 2
        else 0.0
    )
    returns = aligned.pct_change().dropna()
    correlation = (
        float(returns["primary"].corr(returns["defensive"]))
        if len(returns) >= 2
        else math.nan
    )

    reasons = []
    if primary_provenance.price_basis != "total_return":
        reasons.append("primary data is not total-return adjusted")
    if defensive_provenance.price_basis != "total_return":
        reasons.append("defensive data is not total-return adjusted")
    if observations < rules.minimum_observations:
        reasons.append(
            f"observations {observations} < {rules.minimum_observations}"
        )
    if years < rules.minimum_years:
        reasons.append(f"years {years:.2f} < {rules.minimum_years:.2f}")
    if overlap_fraction < rules.minimum_overlap_fraction:
        reasons.append(
            f"overlap_fraction {overlap_fraction:.3f} < "
            f"{rules.minimum_overlap_fraction:.3f}"
        )
    if not math.isfinite(correlation):
        reasons.append("return correlation cannot be calculated")

    return MultiAssetAlignment(
        prices=aligned,
        observations=observations,
        years=years,
        overlap_fraction=overlap_fraction,
        return_correlation=correlation,
        decision=GateDecision(passed=not reasons, reasons=tuple(reasons)),
    )

