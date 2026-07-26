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
metrics, each fold's selected parameters, and every rejection reason.

Research results are not guarantees of future returns. Transaction costs,
slippage, liquidity, and out-of-sample validation must be included before any
strategy is considered for live testing.
