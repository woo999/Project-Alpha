import pandas as pd

from project_alpha.stability import (
    StabilityCriteria,
    analyze_parameter_stability,
)


def make_table(scores: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "candidate_index": range(len(scores)),
            "fast_window": [5, 10, 15, 20, 25][: len(scores)],
            "slow_window": [30, 40, 50, 60, 70][: len(scores)],
            "selection_score": scores,
        }
    )


def test_smooth_parameter_region_passes():
    report = analyze_parameter_stability(
        make_table([0.8, 1.0, 1.1, 0.95, 0.75]),
        selected_candidate_index=2,
    )

    assert report.passed
    assert report.neighbor_count == 4
    assert report.passing_fraction >= 0.5
    assert report.peak_ratio < 3.0


def test_isolated_score_spike_is_rejected():
    report = analyze_parameter_stability(
        make_table([0.8, 1.0, 10.0, 0.9, 0.7]),
        selected_candidate_index=2,
    )

    assert not report.passed
    assert any("passing_fraction" in reason for reason in report.reasons)
    assert any("peak_ratio" in reason for reason in report.reasons)


def test_too_few_neighbors_is_rejected():
    criteria = StabilityCriteria(
        neighbors_to_check=2,
        minimum_neighbors=2,
    )
    report = analyze_parameter_stability(
        make_table([1.0, 1.1]),
        selected_candidate_index=1,
        criteria=criteria,
    )

    assert not report.passed
    assert any("neighbor_count" in reason for reason in report.reasons)
