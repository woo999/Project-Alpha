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

Research results are not guarantees of future returns. Transaction costs,
slippage, liquidity, and out-of-sample validation must be included before any
strategy is considered for live testing.
