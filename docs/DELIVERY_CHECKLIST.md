# Investing, trading and Momentum delivery

User objective: a personal Indian-equity platform for growth investing and trading, with agents, performance-based decisions, and source-linked news summaries in the existing private Momentum OS site. Starting planning capital is INR 10,000 plus at least INR 2,000 monthly. Trading horizon initially defaults to swing trading, subject to evaluation. No profitability claim or fabricated evidence is an acceptance criterion.

## Completion evidence required

- [ ] Existing Momentum planner preserved; finance section usable on desktop and mobile.
- [ ] Private authenticated storage for budget, watchlist, research history and paper trades.
- [ ] Low-price affordability distinct from market cap and valuation; growth screen handles missing evidence explicitly.
- [ ] Existing fin-AAI evidence imported with provenance and refresh timestamps; broader-universe coverage correctly reported.
- [ ] Fresh market history and company announcements reachable from the hosted runtime, with errors and stale data surfaced.
- [ ] Fundamentals, governance, valuation and synthesis agents run against the same frozen evidence; citations and outputs validated; outcomes recorded.
- [ ] News digest produces source-linked summaries and distinguishes supplied facts from interpretation.
- [ ] Deterministic backtest with no future-data signals, next-session fills, costs, gaps, integer sizing, risk controls and out-of-sample metrics.
- [ ] Paper positions and realised/unrealised results remain distinct from backtests and real-money holdings.
- [ ] Portfolio proposals respect the user's budget and require user decisions; no unauthorised broker orders.
- [ ] Relevant financial calculation, storage, authentication, failure-path and integration checks pass.
- [ ] Complete site built, privately published to Momentum, and production route/data/storage/agent behaviour verified.
- [ ] Operational limitations, source coverage, refresh workflow and outstanding performance validation documented truthfully.

## Current verification

2026-09-10: Existing Python research suite passed 67 tests during status review. Momentum source cloned into `momentum-site`; dependencies installed. Initial finance route returned HTTP 200 locally at port 5173. All other completion items remain unproven.

## Current verification (2026-09-26)

- Root source is committed locally through `28b6381`; the configured GitHub remote remains at the original first commit because publication awaits explicit authorization.
- Windows pre-market and post-market tasks are registered and Ready.
- Official refresh through 2026-09-25 updated 499/500 discovery symbols and made all ten pilot financial profiles ready.
- Momentum version 45 is privately deployed; local build and application suite passed 40 tests.
- Python research suite passed 77 tests; trading workstream passed its 21 tests.
- The latest trading promotion gate remains `not_eligible` at 19 holdout trades.
- Provider variables are missing; the current ITC report is explicitly `provider_required` and issues no recommendation.

## Status note (2026-09-24)
This checklist records the 2026-09-10 baseline. For current goals, status and execution order, use [CONSOLIDATED_GOALS.md](CONSOLIDATED_GOALS.md) and [PROJECT_LOG.md](../PROJECT_LOG.md).



