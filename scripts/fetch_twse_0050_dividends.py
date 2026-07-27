"""Download official 0050 cash-dividend events to a corporate-action CSV."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from project_alpha.twse_dividends import fetch_twse_etf_dividends


ETF_0050_SPLIT_DATE = "2025-06-18"
ETF_0050_SPLIT_RATIO = 4.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--start-year", type=int, default=2006)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    args = parser.parse_args()

    dividends = fetch_twse_etf_dividends(
        "0050", args.start_year, args.end_year
    )
    actions = dividends.loc[:, ["cash_dividend"]].copy()
    actions.insert(0, "split_ratio", 1.0)
    if args.start_year <= 2025 <= args.end_year:
        actions.loc[ETF_0050_SPLIT_DATE, ["split_ratio", "cash_dividend"]] = [
            ETF_0050_SPLIT_RATIO,
            0.0,
        ]
        actions.index = pd.DatetimeIndex(actions.index)
        actions = actions.sort_index()
    actions.index.name = "date"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    actions.reset_index().to_csv(args.output, index=False)
    print(
        f"saved {len(actions)} official 0050 corporate-action events "
        f"from {actions.index[0].date()} to {actions.index[-1].date()}"
    )


if __name__ == "__main__":
    main()
