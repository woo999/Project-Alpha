import pandas as pd
import pytest

from project_alpha.data_io import load_price_csv


def test_load_price_csv_preserves_chronological_rows(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text(
        "timestamp,close\n2024-01-01,100\n2024-01-02,101\n",
        encoding="utf-8",
    )

    prices = load_price_csv(path)

    assert prices.tolist() == [100, 101]
    assert isinstance(prices.index, pd.DatetimeIndex)
    assert prices.index.is_monotonic_increasing


def test_load_price_csv_rejects_missing_columns(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text("date,price\n2024-01-01,100\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing columns"):
        load_price_csv(path)


def test_load_price_csv_rejects_duplicate_timestamps(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text(
        "timestamp,close\n2024-01-01,100\n2024-01-01,101\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate timestamps"):
        load_price_csv(path)
