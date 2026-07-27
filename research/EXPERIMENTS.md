# Project Alpha Experiment Ledger

This append-only ledger records every real-market experiment, including failed
ones. The 2010-01-04 through 2026-07-24 Taiwan 50 history has now been inspected
and must not be described as a pristine future confirmation set for later ideas.

| ID | Rule | Selection | Result | Main rejection reasons |
|---|---|---|---|---|
| EXP-001 | SMA long/cash | Parameters reselected in each expanding fold | Rejected | 28.0% maximum drawdown, 46.2% positive folds, all cost scenarios failed |
| EXP-002 | Fixed 20/200 SMA crossover | Declared once; no fold reselection | Rejected | 27.6% maximum drawdown, 0% fold pass rate, all cost scenarios failed |
| EXP-003 | Price above 200-day SMA | Declared once; no fold reselection | Rejected | 21.1% maximum drawdown, 23.1% fold pass rate, all cost scenarios failed |
| EXP-004 | Price above 200-day SMA with unlevered volatility scaling | Predeclared 10%, 12.5%, and 15% volatility sensitivity set | Rejected | 10% target survived the base gate but failed stressed costs and fold consistency; no target passed all gates |
| EXP-005 | 12.5% volatility target, rebalanced every 5 days with a 5 percentage-point no-trade buffer | One predeclared cost-control variant compared with daily rebalancing on user-supplied 0050 daily data | Rejected | Turnover fell 32.4% and drawdown improved from 25.8% to 22.1%, but Sharpe was 0.432, fold pass rate was 18.8%, and all cost-stress scenarios failed |
| EXP-006 | 252-day absolute momentum, checked every 21 trading days | One predeclared monthly low-turnover rule; no parameter search | Rejected | 34.3% maximum drawdown, 0% fold pass rate, lagged buy-and-hold by 250.3 percentage points, and all cost-stress scenarios failed |
| EXP-007 | 70% permanent 0050 core plus 30% 200-day trend sleeve, checked every 5 days | One predeclared core-protection rule; no weight or window search | Rejected | 30.1% maximum drawdown, 0% fold pass rate, Sharpe 0.002 below buy-and-hold, and all cost-stress scenarios failed |

Passing an exploratory result would still not authorize live trading. A
candidate must next survive paper trading on observations that were unavailable
when the rule was chosen.

EXP-005 used 5,000 raw 0050 observations from 2006-03-20 through 2026-07-27.
Prices before the 2025-06-18 1-for-4 split were divided by four to remove the
mechanical split jump. The source was not dividend-adjusted, so this experiment
is useful for rejecting the candidate but is not a total-return confirmation.
