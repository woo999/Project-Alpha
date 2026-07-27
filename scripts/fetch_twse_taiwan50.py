"""Download official Taiwan 50 price and total-return indices to local CSV."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from project_alpha.twse_data import fetch_taiwan50_total_return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2010, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()

    frame = fetch_taiwan50_total_return(args.start, args.end)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.reset_index().to_csv(args.output, index=False)
    print(
        f"saved {len(frame)} official observations "
        f"from {frame.index[0].date()} to {frame.index[-1].date()}"
    )


if __name__ == "__main__":
    main()
