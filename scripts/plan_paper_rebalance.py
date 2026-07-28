"""Print a scheduled paper-rebalance plan without placing an order."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from project_alpha.paper_snapshot_io import load_paper_ledger
from project_alpha.paper_update import append_scheduled_rebalance


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Calculate a scheduled offline paper rebalance. This command "
            "does not connect to a broker, place orders, or modify the ledger."
        )
    )
    parser.add_argument("preregistration", type=Path)
    parser.add_argument("observations", type=Path)
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--primary-close", type=float, required=True)
    parser.add_argument("--defensive-close", type=float, required=True)
    parser.add_argument("--primary-dividend", type=float, default=0.0)
    parser.add_argument("--defensive-dividend", type=float, default=0.0)
    args = parser.parse_args()

    ledger = load_paper_ledger(args.preregistration, args.observations)
    previous = ledger.observations[-1]
    result = append_scheduled_rebalance(
        ledger,
        observed_on=args.date,
        primary_close=args.primary_close,
        defensive_close=args.defensive_close,
        primary_cash_dividend=args.primary_dividend,
        defensive_cash_dividend=args.defensive_dividend,
    )
    plan = {
        "mode": "OFFLINE_PAPER_PLAN_ONLY",
        "observation_number": len(ledger.observations),
        "observed_on": result.observed_on,
        "action": "REBALANCE" if result.turnover_today > 0 else "NO_TRADE",
        "primary": {
            "symbol": ledger.spec.primary_symbol,
            "units_before": previous.primary_units,
            "units_after": result.primary_units,
            "unit_change": result.primary_units - previous.primary_units,
            "weight_after": result.primary_weight,
        },
        "defensive": {
            "symbol": ledger.spec.defensive_symbol,
            "units_before": previous.defensive_units,
            "units_after": result.defensive_units,
            "unit_change": result.defensive_units - previous.defensive_units,
            "weight_after": result.defensive_weight,
        },
        "gross_turnover": result.turnover_today,
        "charged_transaction_costs": result.charged_transaction_costs_today,
        "cash_after": result.cash_balance,
        "portfolio_value_after_costs": result.portfolio_value,
        "safety": {
            "broker_connected": False,
            "orders_placed": False,
            "ledger_modified": False,
        },
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
