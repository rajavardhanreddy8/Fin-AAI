# Momentum: real-work status

This file is a visible acceptance record. A claim is complete only when the evidence named below exists and is reproducible from the repository.

## Current state

- **Site:** the private Momentum site is deployed and shows research, trading, news, and run-history surfaces.
- **Research:** official NSE universe refresh and source-backed company evidence reports are implemented.
- **Trading research:** the backtest includes contribution cash flows, fees, slippage, holdout results, and a benchmark.
- **Promotion decision:** the current strategy is **not eligible**. The latest aggregate holdout has too few trades for a reliable promotion decision.
- **Paper trading:** the scheduler is distinct from backtesting and does not claim that simulated orders were placed.
- **Live execution:** no broker is connected and no real-money order path is enabled.
- **Provider:** the external research model is not configured; provider-dependent research must report `provider_required`.
- **Repository export:** the root GitHub repository has not been pushed. The local repository remains the source of truth until explicit authorization names the exact destination and branch.

## Work required for completion

1. Refresh and validate price, fundamentals, filings, corporate actions, and symbol mappings with dated hashes.
2. Run walk-forward and regime-separated evaluation with realistic costs and enough independent trades.
3. Run the same strategy code in a paper ledger for 8–12 weeks, recording signals, intended orders, fills, costs, stops, and reasons.
4. Enforce portfolio limits, loss limits, stale-data checks, and an operator kill switch.
5. Publish a dated report for every run, including inputs, code commit, parameters, trades, benchmark, drawdown, and promotion decision.
6. Only after the paper gate passes, test a broker sandbox with human approval before considering minimal live capital.

## Evidence commands

Run from the repository root:

```powershell
python scripts\verify_finance_system.py --full
python -m pytest -q
```

The first command writes `output/finance-system-full-verification.json`. A passing test suite alone does not make a strategy investable; the promotion gate and paper ledger must also pass.

## Honest completion rule

The project is complete only when the verification report, paper-trading ledger, risk-control checks, and deployment status all pass together. Until then, the dashboard must continue to show a non-promoted or provider-required state.
