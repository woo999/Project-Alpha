"""Parameter-neighborhood checks for detecting isolated backtest peaks."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd


@dataclass(frozen=True)
class StabilityCriteria:
    neighbors_to_check: int = 4
    minimum_neighbors: int = 2
    minimum_neighbor_score_ratio: float = 0.50
    minimum_passing_fraction: float = 0.50
    maximum_peak_ratio: float = 3.0

    def validate(self) -> None:
        if self.neighbors_to_check < 1:
            raise ValueError("neighbors_to_check must be positive")
        if self.minimum_neighbors < 1:
            raise ValueError("minimum_neighbors must be positive")
        if self.minimum_neighbors > self.neighbors_to_check:
            raise ValueError("minimum_neighbors cannot exceed neighbors_to_check")
        if not 0.0 <= self.minimum_neighbor_score_ratio <= 1.0:
            raise ValueError("minimum_neighbor_score_ratio must be in [0, 1]")
        if not 0.0 <= self.minimum_passing_fraction <= 1.0:
            raise ValueError("minimum_passing_fraction must be in [0, 1]")
        if self.maximum_peak_ratio < 1.0:
            raise ValueError("maximum_peak_ratio must be at least one")


@dataclass(frozen=True)
class StabilityReport:
    passed: bool
    selected_candidate_index: int
    selected_score: float
    neighbor_count: int
    passing_fraction: float
    median_neighbor_score: float
    peak_ratio: float
    neighbor_candidate_indices: tuple[int, ...]
    reasons: tuple[str, ...]


def analyze_parameter_stability(
    candidate_table: pd.DataFrame,
    selected_candidate_index: int,
    criteria: StabilityCriteria | None = None,
) -> StabilityReport:
    """Reject a winner whose nearest parameter neighbors collapse."""
    rules = criteria or StabilityCriteria()
    rules.validate()
    required = {
        "candidate_index",
        "fast_window",
        "slow_window",
        "selection_score",
    }
    missing = required.difference(candidate_table.columns)
    if missing:
        raise ValueError(f"candidate table is missing columns: {sorted(missing)}")
    if candidate_table.empty:
        raise ValueError("candidate table cannot be empty")
    if candidate_table["candidate_index"].duplicated().any():
        raise ValueError("candidate_index values must be unique")

    table = candidate_table.copy()
    for column in ("fast_window", "slow_window", "selection_score"):
        table[column] = pd.to_numeric(table[column], errors="raise").astype(float)
        if not table[column].map(math.isfinite).all():
            raise ValueError(f"{column} must contain only finite values")

    selected_rows = table[table["candidate_index"] == selected_candidate_index]
    if len(selected_rows) != 1:
        raise ValueError("selected candidate index was not found")
    selected = selected_rows.iloc[0]
    selected_score = float(selected["selection_score"])

    others = table[table["candidate_index"] != selected_candidate_index].copy()
    fast_scale = max(abs(float(selected["fast_window"])), 1.0)
    slow_scale = max(abs(float(selected["slow_window"])), 1.0)
    others["_distance"] = (
        (others["fast_window"] - float(selected["fast_window"])).abs() / fast_scale
        + (others["slow_window"] - float(selected["slow_window"])).abs() / slow_scale
    )
    neighbors = others.sort_values(
        ["_distance", "candidate_index"],
        kind="stable",
    ).head(rules.neighbors_to_check)

    neighbor_count = len(neighbors)
    neighbor_scores = neighbors["selection_score"]
    median_neighbor_score = (
        float(neighbor_scores.median()) if neighbor_count else float("nan")
    )
    if selected_score > 0.0 and neighbor_count:
        threshold = selected_score * rules.minimum_neighbor_score_ratio
        passing_fraction = float((neighbor_scores >= threshold).mean())
        peak_ratio = (
            selected_score / median_neighbor_score
            if median_neighbor_score > 0.0
            else math.inf
        )
    else:
        passing_fraction = 0.0
        peak_ratio = math.inf

    reasons: list[str] = []
    if selected_score <= 0.0:
        reasons.append("selected score must be positive")
    if neighbor_count < rules.minimum_neighbors:
        reasons.append(
            f"neighbor_count {neighbor_count} < {rules.minimum_neighbors}"
        )
    if passing_fraction < rules.minimum_passing_fraction:
        reasons.append(
            f"passing_fraction {passing_fraction:.2f} < "
            f"{rules.minimum_passing_fraction:.2f}"
        )
    if peak_ratio > rules.maximum_peak_ratio:
        reasons.append(
            f"peak_ratio {peak_ratio:.2f} > {rules.maximum_peak_ratio:.2f}"
        )

    return StabilityReport(
        passed=not reasons,
        selected_candidate_index=selected_candidate_index,
        selected_score=selected_score,
        neighbor_count=neighbor_count,
        passing_fraction=passing_fraction,
        median_neighbor_score=median_neighbor_score,
        peak_ratio=peak_ratio,
        neighbor_candidate_indices=tuple(
            int(value) for value in neighbors["candidate_index"].tolist()
        ),
        reasons=tuple(reasons),
    )
