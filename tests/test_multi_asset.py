import pandas as pd
import pytest

from project_alpha.multi_asset import (
    MultiAssetCriteria,
    align_multi_asset_prices,
)
from project_alpha.promotion import DataProvenance


def provenance(symbol, basis="total_return"):
    return DataProvenance(
        source_name="test",
        symbol=symbol,
        price_basis=basis,
    )


def test_alignment_uses_only_shared_dates_without_forward_fill():
    primary_dates = pd.date_range("2015-01-01", periods=12, freq="YS")
    defensive_dates = primary_dates.delete(3)
    primary = pd.Series(range(100, 112), index=primary_dates)
    defensive = pd.Series(range(80, 91), index=defensive_dates)

    result = align_multi_asset_prices(
        primary,
        defensive,
        provenance("PRIMARY"),
        provenance("DEFENSIVE"),
        MultiAssetCriteria(
            minimum_observations=252,
            minimum_years=1,
            minimum_overlap_fraction=0.9,
        ),
    )

    assert len(result.prices) == 11
    assert primary_dates[3] not in result.prices.index
    assert result.prices.isna().sum().sum() == 0


def test_non_total_return_defensive_asset_cannot_pass():
    dates = pd.date_range("2015-01-01", periods=2200, freq="B")
    primary = pd.Series(range(100, 2300), index=dates)
    defensive = pd.Series(range(80, 2280), index=dates)

    result = align_multi_asset_prices(
        primary,
        defensive,
        provenance("PRIMARY"),
        provenance("DEFENSIVE", basis="raw"),
    )

    assert result.decision.passed is False
    assert "not total-return adjusted" in result.decision.reasons[0]


def test_duplicate_dates_are_rejected():
    dates = pd.DatetimeIndex(["2020-01-01", "2020-01-01"])
    duplicate = pd.Series([100.0, 101.0], index=dates)
    valid = pd.Series(
        [80.0, 81.0],
        index=pd.DatetimeIndex(["2020-01-01", "2020-01-02"]),
    )

    with pytest.raises(ValueError, match="duplicate"):
        align_multi_asset_prices(
            duplicate,
            valid,
            provenance("PRIMARY"),
            provenance("DEFENSIVE"),
        )
