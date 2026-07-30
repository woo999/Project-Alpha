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

## Authenticated paper status and readiness

All paper commands verify the published tamper-evident snapshot before trusting
the ledger. This read-only status command cannot connect to a broker or place
orders:

```powershell
$env:PYTHONPATH = "src"
python scripts\report_paper_status.py `
  research\preregistration.json `
  data\paper_observations.csv `
  research\paper_snapshot.json
```

After exporting both Mitake daily files, check the next paper date against the
authenticated ledger and the free TWSE/TPEx closing feeds:

```powershell
python scripts\check_official_close_readiness.py 2026-07-29 `
  --primary-export C:\path\to\0050__D.txt `
  --defensive-export C:\path\to\00719B__D.txt
```

The readiness command is read-only. It reports `ready: true` only when the
snapshot, single-day sequence, symbols, dates, and both official closing prices
agree. Evidence creation and ledger writes remain separate guarded steps. The
paper ledger is research-only, prohibits leverage and broker connectivity, and
is not evidence of live readiness.
