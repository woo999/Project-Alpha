"""Download and verify official TPEx distribution evidence from a CSV manifest."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path

from project_alpha.tpex_exright import TPEX_EXRIGHT_API, fetch_tpex_distribution


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--symbol", required=True)
    args = parser.parse_args()

    expected: list[tuple[date, float]] = []
    with args.manifest.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None or "cash_dividend" not in reader.fieldnames:
            raise ValueError("manifest must contain cash_dividend")
        date_field = "ex_date" if "ex_date" in reader.fieldnames else "date"
        if date_field not in reader.fieldnames:
            raise ValueError("manifest must contain date or ex_date")
        for row in reader:
            event_date = date.fromisoformat(row[date_field])
            amount = float(row["cash_dividend"])
            if not math.isfinite(amount) or amount <= 0:
                raise ValueError("manifest dividends must be finite and positive")
            expected.append((event_date, amount))
    if not expected:
        raise ValueError("manifest cannot be empty")
    if [event[0] for event in expected] != sorted({event[0] for event in expected}):
        raise ValueError("manifest dates must be unique and chronological")

    records = []
    for event_date, expected_amount in expected:
        record = fetch_tpex_distribution(symbol=args.symbol, ex_date=event_date)
        if not math.isclose(record.cash_dividend, expected_amount, abs_tol=1e-12):
            raise ValueError(
                f"TPEx dividend conflict on {event_date}: "
                f"{record.cash_dividend} != {expected_amount}"
            )
        records.append(
            {
                **record.to_dict(),
                "request": {
                    "method": "POST",
                    "startDate": event_date.strftime("%Y/%m/%d"),
                    "endDate": event_date.strftime("%Y/%m/%d"),
                    "response": "json",
                },
            }
        )

    report = {
        "source": TPEX_EXRIGHT_API,
        "authority": "Taipei Exchange (TPEx)",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "expected_events": len(expected),
        "verified_events": len(records),
        "all_amounts_match": True,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
