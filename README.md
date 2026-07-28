# Project Alpha

Python research workspace for developing and validating systematic trading ideas.

## Project structure

- `src/` — reusable research and trading code
- `data/` — local datasets (large and sensitive files are ignored)
- `notebooks/` — exploratory research notebooks
- `tests/` — automated tests

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest
```

## Run walk-forward validation on a CSV

The CSV must contain chronological `timestamp` and `close` columns. Data is
read locally; this command does not connect to a broker or place orders.

```powershell
$env:PYTHONPATH = "src"
python -m project_alpha.cli data\prices.csv --min-train 504 --test-size 63
```

For intraday data, set the number of bars in a trading year and provide
appropriate transaction-cost assumptions:

```powershell
python -m project_alpha.cli data\prices_5m.csv `
  --min-train 3000 `
  --test-size 500 `
  --periods-per-year 13500 `
  --fee-rate 0.001 `
  --slippage-rate 0.0005
```

The JSON report states `mode: research_only`, the aggregate out-of-sample
metrics, each fold's selected parameters, and every rejection reason. It also
reprices the same unseen trades at 1.0x, 1.5x, and 2.0x the assumed transaction
costs; by default, every cost scenario must pass. A separate frictionless
buy-and-hold comparison reports excess return and improvements in drawdown,
Sharpe, and Calmar without yet applying an arbitrary benchmark gate.

## Official Taiwan 50 research data

Download the free Taiwan Stock Exchange Taiwan 50 price index and total-return
index. The `close` column is the total-return index, not a tradable 0050 quote.

```powershell
$env:PYTHONPATH = "src"
python scripts\fetch_twse_taiwan50.py data\taiwan50_total_return.csv `
  --start 2010-01-01
```

The downloader validates the official response schema, ROC dates, chronological
order, and duplicate dates before saving. This dataset is suitable for an
initial market-level study; final 0050 execution research still requires
adjusted ETF prices and ETF-specific costs.

Research results are not guarantees of future returns. Transaction costs,
slippage, liquidity, and out-of-sample validation must be included before any
strategy is considered for live testing.

## Offline paper-ledger checkpoint

After a preregistration is explicitly marked `PAPER_TRACKING_ACTIVE`, validate
the local observation CSV and write a deterministic, tamper-evident checkpoint:

```powershell
$env:PYTHONPATH = "src"
python scripts\snapshot_paper_ledger.py `
  research\0050_00719B_60_40_preregistration.json `
  data\paper_observations.csv `
  research\paper_snapshot.json
```

The CSV schema is fixed to `observed_on, portfolio_value, primary_close,
defensive_close, primary_units, defensive_units, cash_balance, turnover_today,
charged_transaction_costs_today`. The command refuses blocked candidates,
historical or duplicate dates, unreconciled positions, off-schedule turnover,
understated costs, and off-target rebalance weights. It reads and writes local
files only and cannot connect to a broker or place orders.
