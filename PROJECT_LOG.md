# Project Log — fin-AAI

## Current summary

- **Project description:** fin-AAI serves one owner who wants to research Indian shares and test trading ideas from a small account without confusing a plausible story with verified evidence. The private Momentum finance workspace displays a dated Nifty 500 discovery list, source-linked company research, historical daily-bar tests, a forward paper ledger, and filing digests. A Python pipeline collects exchange and company documents, verifies company identity, document provenance and freshness, computes financial facts and governance checks, and can send a bounded evidence packet to a configured language model for a cited report. The owner reviews the results and makes decisions; the system does not place broker orders. The 500-company discovery list currently has only 10 complete research profiles. See [consolidated goals and execution order](docs/CONSOLIDATED_GOALS.md) for the full workflow and prioritized backlog.
- **Goal and success criteria:** Make investing research and trading evaluation genuinely usable in Momentum: current attributable evidence and explicit missing-data labels; inspectable saved research reports; reproducible backtests with realistic costs and benchmarks; forward paper outcomes; source-linked digests; and measured forecast/research quality over time. Use ₹10,000 starting capital and a planned ₹2,000 monthly contribution for experiments. Expand verified coverage toward the selected Nifty 500 universe without treating identity coverage as research coverage. A day-wise, 30-minute hands-on finance/markets/agents/ML course is a supporting goal. Profitability is a hypothesis to test, not a completion claim.
- **Scope and constraints:** Discovery has 500 NSE identities; source-linked financial coverage is 10 profiles at the latest recorded checkpoint. Market history is end-of-day exploratory data, not an execution feed. Investing research, historical backtests, forward paper activity and any future holdings remain separate. Groq/OpenRouter secrets belong server-side. Pre-market/post-market agents and broker integration require their own verification; live orders, autonomous fund transfers, invented target prices and profit guarantees are outside current scope. Broker selection remains deferred until backtest and forward paper evidence is reviewed.
- **Current status:** In progress; reconciled 2026-09-24 Asia/Kolkata against recorded task outcomes and repository files, without a fresh production audit. Momentum version 44 is the latest observed private version; this turn did not redeploy the Site. The latest task found no saved investing research review or verified forward paper record. A local Codex weekday pre/post schedule is now active, but its first complete official-source cycle is pending. The latest read-only 10-symbol historical evaluator remains not eligible at 19 holdout trades versus 30 required and a negative mean strategy return. The root repository still contains substantial untracked work even though the nested Momentum repository was reported pushed.
- **Checkpoints:**
  - **C001 — Official-source collection and normalization:** Complete. Ten-company dataset with financial, ownership, price, and governance data.
  - **C002 — Cloud synchronization and provenance audit:** Complete. Supabase synchronization completed with zero financial facts missing document provenance.
  - **C003 — Automated regression verification:** Complete for the recorded scope. The Python research suite passed 67 tests on 2026-09-13; later Momentum changes passed their own application suite before deployment.
  - **C004 — Provider-independent recommendation workflow:** Complete. The CLI recommendation path passed its 66-test suite and an insufficient-evidence smoke test without calling a model.
  - **C005 — Live provider validation:** Open. The Python CLI has no verified live model run. A Momentum OpenRouter company-review attempt reached the provider but failed with HTTP 413; the compact request and deterministic fallback were deployed afterward, but no successful saved review was verified.
  - **C006 — Fresh collection orchestration:** Complete. `research-recommendation --refresh-current-evidence` explicitly runs official-source refresh, deterministic validation, and then recommendation generation.
  - **C007 — Momentum investing and trading workspace:** Complete as a deployed interface. The private site provides evidence coverage filtering, daily-bar backtests, contribution-aware cost modelling, a forward paper ledger, bounded company research, and source-linked NSE notice digests.
  - **C008 — Saved research and strategy evidence:** In progress. No saved company review or forward paper record was verified in the latest status task; the current historical rule failed the real-capital promotion gate.
  - **C009 — Nifty 500 research coverage:** In progress. Dated identity discovery exists for 500 companies; full source-linked financial coverage remains at 10 verified profiles.
  - **C010 — Scheduled daily agents and outcome scoring:** Local weekday 8:30 AM and 5:00 PM Asia/Kolkata heartbeat is active. The new runner records idempotent pre/post jobs, official-source refresh attempts, prospective baseline forecasts, exact-session scoring and a read-only strategy evaluation. The first complete scheduled market-day cycle and local model connection remain unverified; the Momentum paper ledger is still on demand.
  - **C011 — Practical learning course:** Requested. A completed day-wise, 30-minute course was not visible in the related task history.
- **Next actions and open questions:** Inspect the first scheduled pre/post reports and official-source coverage; configure the separate local Groq runtime if model synthesis is wanted; verify current saved finance records and one cited company review; freeze and test a revised trading rule, then build a forward paper record; expand Nifty 500 evidence in batches. Reconcile root Git publication separately. Keep broker selection and live capital deferred until evidence supports a new decision.

## History

### E0001 | 2026-09-06 Asia/Kolkata | Result | Verified Phase 2 completion
- Checkpoint: C001, C002, C003
- Observed result: The verified completion record reports 10 securities, 128 source documents, 455 financial facts, 30 ownership facts, 140 price records, and 5 governance flags synchronized to Supabase.
- Evidence: Prior project task, “Run and push to new repo,” reported all ten companies passed readiness checks, clean provenance, and 63 passing tests.
- Follow-up: Treat subsequent refreshes or repository publication as new work events.

### E0002 | 2026-09-06 17:15 Asia/Kolkata | Correction | Product goal extends beyond Phase 2
- Related event: E0001
- Correction: E0001 accurately records completion of the data-foundation phase, but it does not represent completion of fin-AAI as a working recommendation agent.
- Evidence: README previously stated that the repository did not generate recommendations, while the clarified product goal requires fresh evidence to feed an LLM-backed recommendation workflow.
- Follow-up: Track recommendation workflow and live-provider verification under C004 and C005.

### E0003 | 2026-09-06 17:15 Asia/Kolkata | Progress | Provider-neutral research-agent path implemented
- Checkpoint: C004
- Observed result: Added a standard-library OpenAI-compatible HTTP adapter, evidence-packet builder, deterministic positive-action gates, source-citation validation, append-only recommendation persistence, Markdown report generation, and CLI entry point. Missing evidence returns before any model call.
- Evidence: `src/stock_research/research_agent.py`, `tests/test_research_agent.py`, and the `research-recommendation` CLI command.
- Follow-up: Run the complete suite and validate against the confirmed live provider.

### E0004 | 2026-09-06 17:17 Asia/Kolkata | Result | Provider-neutral workflow verified
- Related event: E0003
- Observed result: The full 66-test suite passed. A real CLI smoke run for NTPC returned `insufficient_evidence`, identified the missing matching annual report, wrote a timestamped evidence report, exited with code 2, and did not require or call an LLM.
- Evidence: `python -m unittest discover -s tests -v`; `research-recommendation` CLI output at `C:\tmp\fin-aai-ntpc-insufficient.md`.
- Follow-up: Confirm the intended provider and perform one live model smoke test with server-only environment variables.

### E0005 | 2026-09-06 Asia/Kolkata | Result | Current-date evidence refresh and orchestration verified
- Checkpoint: C006
- Observed result: The isolated refresh database contains all 10 securities and official NSE EOD rows through Friday 2026-09-04, the latest trading session before the Sunday 2026-09-06 as-of date. All ten companies pass deterministic readiness against the refreshed database. The recommendation command now has an explicit `--refresh-current-evidence` path that refreshes EOD prices, shareholding, annual reports, and annual iXBRL financials before validation and model invocation.
- Evidence: `C:\tmp\fin-aai-live-2026-09-06.db`; `src/stock_research/cli.py`; focused `test_cli_phase2.py` run completed 6 tests with OK.
- Limitation: The current evidence set contains 128 documents, 455 financial facts, 30 ownership facts, 140 price bars, and 5 governance flags. Freshness is EOD, not streaming. A live recommendation was not generated because `RESEARCH_LLM_BASE_URL`, `RESEARCH_LLM_API_KEY`, and `RESEARCH_LLM_MODEL` are intentionally unset pending provider confirmation.
- Follow-up: Confirm the provider and configure its credentials server-side, then run one live cited recommendation smoke test.



### E0006 | 2026-09-13 Asia/Kolkata | Result | Private Momentum finance workspace deployed
- Checkpoint: C007
- Observed result: Momentum version 21 was privately deployed at https://momentum-os.rajavreddy-g.chatgpt.site after the production build and 35 automated application tests passed. The release includes evidence-ready filtering for 10 of 500 identities, contribution-aware historical tests, a forward paper ledger, filing digest, and encrypted Groq/OpenRouter finance-model connections.
- Evidence: Saved version appgver_016f3dbf59648191ad815c53b8694a1b; deployment appgdep_6aa605d340c08191b6dac33438f0bb4e reported succeeded.
- Follow-up: Connect a provider in Settings and collect real paper-trading observations before selecting a broker or using real capital.


### E0007 | 2026-09-13 Asia/Kolkata | Result | Research pipeline verification refreshed
- Checkpoint: C003, C004, C006
- Observed result: The full source-backed Python research suite passed: 67 tests in 7.619 seconds. The first direct command failed only because the repository requires its documented PYTHONPATH=src setting; rerunning with that configuration passed all tests.
- Evidence: python -m unittest discover -s tests -v with PYTHONPATH=src.
- Follow-up: This proves fixture-based behavior and source-validation gates, not current market freshness or strategy profitability.


### E0008 | 2026-09-13 Asia/Kolkata | Result | Current official evidence exported to Momentum
- Checkpoint: C007, C008
- Observed result: An isolated official-data refresh for the ten-company research universe completed with all ten companies ready and no blockers. A repeatable export updated the Momentum seed while retaining all 500 discovery identities; each verified profile has an official EOD snapshot through 2026-09-11. Momentum version 22 was privately deployed successfully.
- Evidence: local database C:/tmp/fin-aai-live-2026-09-13.db; source commit cebacb96596d8b287a07abb52ff1547e7a60ba0e; deployment appgdep_6aa608f9e6ec8191aa04ca5a53f25d82.
- Follow-up: The export remains a controlled local refresh step. Connect an LLM provider and gather paper-trading observations before broker selection or real-money use.


### E0009 | 2026-09-13 Asia/Kolkata | Result | Cross-symbol exploratory backtest fails promotion gate
- Checkpoint: C008
- Observed result: The configured daily breakout strategy was run against vendor-adjusted five-year histories for the ten evidence-backed symbols. It produced 22 holdout trades in total; every symbol had fewer than the dashboard's 30-trade minimum, and most net holdout returns were slightly negative after the configured estimates of 20 bps variable fee and 10 bps slippage per side. The strategy is not eligible for real-money use.
- Evidence: Local Vite-loaded strategy run on 2026-09-13; latest completed vendor session was 2026-09-11 for all ten symbols. This is exploratory vendor data, with the source-adjustment limitation retained in the dashboard.
- Follow-up: Do not promote the rule. Improve or replace it only through pre-registered testing, then collect forward paper results before broker selection.


### E0010 | 2026-09-13 Asia/Kolkata | Progress | Strategy gate made visible in Momentum
- Checkpoint: C008
- Observed result: Momentum now imports a generated cross-symbol validation record before the daily breakout controls. The record includes the exact tested universe, assumptions, aggregate holdout trade count, promotion threshold, and limitations. Version 24 deployed privately.
- Evidence: Momentum commit d88323a244152a0dde0b11fd6acc7994fd0b67b4; deployment appgdep_6aa60b76c6508191ba2196bd7235ba06 succeeded.
- Follow-up: Re-run the evaluator only after a pre-registered strategy change or a material new data period; do not optimize repeatedly against the same holdout result.


### E0011 | 2026-09-13 Asia/Kolkata | Result | Strategy promotion gate regression-tested
- Checkpoint: C008
- Observed result: The strategy evaluator now uses a shared tested promotion-gate function. It rejects partial-universe runs and insufficient aggregate samples, while a passing count only advances to review rather than authorizing capital. The refreshed current record remains not eligible at 22 trades.
- Evidence: Momentum commit c4c969f1c05f02b9ace7e96c0e40034d68ee2a6d; deployment appgdep_6aa60c9a99e48191a9c8a17770d4e178 succeeded.
- Follow-up: Complete strategy research only with an independently specified alternative and a new holdout; no current rule qualifies.


### E0012 | 2026-09-14 Asia/Kolkata | Progress | Two finance workstreams made visible in Momentum
- Checkpoint: C007, C008
- Observed result: The private Momentum finance workspace now opens at an Agent Desk that separates investing research from trading validation. Each workstream links to its working controls and states its inputs, saved results, and no-order boundary. The existing strategy gate remains visible as not eligible at 22 holdout trades.
- Evidence: Momentum commit 82762d92ffff927083a365dc5e9e52db20129fc2; full site test suite passed 37/37; private deployment appgdep_6aa7e6a29a74819192cd57edf41db1cb succeeded as Momentum version 30.
- Follow-up: An AI provider connection is still needed for on-demand company reviews and filing digests. Autonomous unattended scheduling has not been provisioned.


### E0013 | 2026-09-14 Asia/Kolkata | Progress | Agent Desk now reports actual readiness
- Checkpoint: C007, C008
- Observed result: The Investing Research card now asks the authenticated server whether Groq or OpenRouter is connected and shows only the selected model name or a connection requirement. Both cards show the user’s latest saved work, so “ready” no longer implies a hidden autonomous job. No secrets are returned to the browser.
- Evidence: Momentum commit 22003fae1eef0048f4ed9d524c21877c32b566a9; full site test suite passed 37/37; private deployment appgdep_6aa7e79e84508191aa541369cb06a596 succeeded as Momentum version 31.
- Follow-up: Connect a provider to make the research agent runnable. A persistent scheduler requires a supported scheduled-runtime binding or an external automation target; no unattended task has been created.


### E0014 | 2026-09-14 Asia/Kolkata | Progress | Agent connection path shortened
- Checkpoint: C007, C008
- Observed result: The finance Agent Desk now links directly to the private Momentum Settings view, where the user can securely connect Groq or OpenRouter. The root view reads the explicit settings query after hydration, avoiding a server/client render mismatch.
- Evidence: Momentum commit 045b99b9e882cb48eb36319710569327b419e823; full site test suite passed 37/37; private deployment appgdep_6aa7e973b7b0819198c10c2ddbea8a50 succeeded as Momentum version 32.
- Follow-up: A user-owned provider key remains required for model execution.


### E0015 | 2026-09-14 Asia/Kolkata | Progress | Official NSE discovery pricing and liquidity screen added
- Checkpoint: C003, C007, C008
- Observed result: A repeatable discovery refresh fetched four official NSE CM-UDiFF sessions through 2026-09-11 for 498 of 500 identity records. Momentum now exposes stored price and close-times-official-volume filters, while evidence-ready remains independently limited to financial facts and source documents. HEG and HFCL were absent from the current EQ bhavcopy and remain explicitly unknown rather than silently substituted.
- Evidence: root script scripts/refresh_finance_discovery_prices.py; Momentum commit b5a3e3a29bfde0af829ef94ee7c822651019b12c; full site test suite passed 37/37; private deployment appgdep_6aa7eb6405108191893e68933845aa1d succeeded as Momentum version 33.
- Follow-up: Discovery output is not an investment screen. Add current company-filing and fundamental evidence before advancing any candidate to the research agent.


### E0016 | 2026-09-14 Asia/Kolkata | Result | Official BE-series exclusions resolved
- Checkpoint: C003, C007
- Observed result: Investigation of the two absent EQ entries found that HEG and HFCL retain their expected ISINs but are listed in the official 2026-09-11 NSE bhavcopy as BE series rather than EQ. Both are now marked with a factual source-linked warning and stay outside the standard EQ discovery filter.
- Evidence: Official NSE bhavcopy https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20260911_F_0000.csv.zip; Momentum commit 2552409a3d19f06f0841136c7c4a1136799c560c; full site test suite passed 37/37; private deployment appgdep_6aa7ec317428819190a00243f860231c succeeded as Momentum version 34.
- Follow-up: Any non-EQ or restricted-series security needs separate tradability and risk review, not normal discovery-screen treatment.


### E0017 | 2026-09-15 Asia/Kolkata | Fix | OpenRouter company-review payload compacted
- Checkpoint: C007, C008
- Observed result: A live ITC research attempt reached the connected provider but received HTTP 413 because the full stored evidence snapshot was about 25 KB and was sent on each specialist call. Research now sends a compact, citation-preserving packet (current core facts, referenced documents, flags, and deterministic assessment) capped by regression testing below 12 KB, while retaining the full frozen snapshot in saved results.
- Evidence: Screenshot supplied by user; Momentum commit 74493f77c2fcabd9837e0a6fe5797df46c1df300; ITC compact-packet regression and full site suite passed; private deployment appgdep_6aa8ca4fef1081919c4c89c3b39bf852 succeeded as Momentum version 36.
- Follow-up: Retry the ITC review. The model still produces research only and cannot establish an investment case or place orders.

### E0018 | 2026-09-15 Asia/Kolkata | Fix | Holdout chart now separates performance from deposits
- Checkpoint: C008
- Observed result: The holdout chart now indexes the strategy and its same-stock buy-and-hold comparison against cumulative contributions, with 100 representing the amount contributed. This prevents monthly deposits from producing an upward visual path while the contribution-adjusted return is negative.
- Evidence: User-supplied Trading Lab screenshot; Momentum commit 140c79c9a390a4ee0f31ad24c0314c841f53dbbf; full site suite passed; private deployment appgdep_6aa8cc1e46d881918f47f8df3d1eea28 succeeded as Momentum version 37.
- Follow-up: The displayed ITC holdout remains one completed trade with a negative return, so it is not eligible for capital.

### E0019 | 2026-09-15 Asia/Kolkata | Fix | Trading Lab now states the capital decision plainly
- Checkpoint: C008
- Observed result: Each single-symbol holdout result now presents a clear decision before the metric cards. A thin sample, a non-positive return, or underperformance against same-stock buy-and-hold explicitly remains outside the practice account; only a positive relative result can advance to broader validation.
- Evidence: User-supplied ICICIBANK and ITC holdout screenshots; Momentum commit 44bafc495de400a1e07625eec420682fea40fa1d; full site suite passed 38/38; private deployment appgdep_6aa8d58d0dd481919d9c03b445d016cc succeeded as Momentum version 38.
- Follow-up: Current ICICIBANK and ITC results both have insufficient samples and negative strategy returns. Continue broad cross-symbol validation rather than treating either as a trading signal.

### E0020 | 2026-09-15 Asia/Kolkata | Fix | Paper validation wording corrected
- Checkpoint: C008
- Observed result: The Trading Lab verdict now correctly distinguishes forward paper testing from real-capital eligibility. Thin or losing holdouts continue into the practice account for evidence collection, while real capital remains disallowed until the wider validation gate is met.
- Evidence: Momentum commit f2d1d91fffa99710bd6aba4622cb7d90e669cfa5; full site suite passed 38/38; private deployment appgdep_6aa8d638bea88191910abd15775d555d succeeded as Momentum version 39.
- Follow-up: Use the paper account to log future rule-based signals. Do not regard either current single-stock holdout as a real-money result.

### E0021 | 2026-09-15 Asia/Kolkata | Fix | Strategy promotion now requires quality, not just trade count
- Checkpoint: C008
- Observed result: The promotion gate now rejects a fully evaluated, sufficiently large sample if its equal-weight holdout return is non-positive or it fails to beat the same-stock buy-and-hold comparison. Momentum displays the mean strategy, benchmark, and excess returns next to the trade-count gate.
- Evidence: Fresh 10-symbol strategy evaluation: 22 trades, -0.388% mean strategy return, -8.892% mean benchmark return, +8.504% mean excess return; dedicated promotion tests 3/3 and full suite passed; Momentum commit c7c91bbe85b74fec00721c3c20b68f9b98c773dc; private deployment appgdep_6aa8d7a3705c8191b1a627b13cf5316f succeeded as version 40.
- Follow-up: The current rule remains ineligible due to an insufficient 22-trade sample and negative mean strategy return. It requires a revised rule or more evidence, then forward paper results before any capital review.

### E0022 | 2026-09-15 Asia/Kolkata | Progress | Cross-symbol results are inspectable in Momentum
- Checkpoint: C008
- Observed result: Trading Lab now exposes the per-symbol trades, strategy returns, buy-and-hold returns, and maximum drawdowns underlying the aggregate promotion gate. This lets the user review the ten historical inputs rather than relying on a single aggregate status.
- Evidence: Momentum commit 3547aa6342488fd3e2a0dca018ffaac1d0c4c364; full site suite passed; private deployment appgdep_6aa8d86f8a8c8191ba45a5608b67150d succeeded as version 41.
- Follow-up: The table is historical evidence only. The next meaningful decision is whether a revised, independently specified rule can pass the same gate, followed by forward paper validation.

### E0023 | 2026-09-15 Asia/Kolkata | Fix | Research review survives model-provider failures
- Checkpoint: C007, C008
- Observed result: A company review now saves a clearly labelled deterministic evidence review when the connected research model is unavailable or rejects the request. The fallback retains the frozen evidence snapshot, source IDs, comparable growth facts, governance flags, and unanswered diligence questions; it makes no valuation or investment recommendation.
- Evidence: Finance-research fallback test passed 5/5; production build passed; Momentum commit ced90f0a10ba4f2989f629268e26a7e7c2b40542; private deployment appgdep_6aa8d99b48988191b35162a853eba425 succeeded as version 42.
- Follow-up: Rerun the ITC review. A successful model call produces the specialist synthesis; a provider failure now still produces a saved source-cited evidence review.

### E0024 | 2026-09-15 Asia/Kolkata | Progress | Discovery results can be sorted for review
- Checkpoint: C003, C007
- Observed result: Growth Research now lets the user sort filtered company discovery results by research readiness, lowest stored price, or highest stored turnover. This changes review order only and does not turn price or turnover into a recommendation.
- Evidence: Momentum commit cb4010fc5509f701248182a138b2b3caa500fb8c; full site suite passed; private deployment appgdep_6aa8dab657f08191a1c41561c49ad55d succeeded as version 43.
- Follow-up: Apply a price and turnover filter, then use evidence readiness and original filings to decide what deserves research.

### E0025 | 2026-09-24 10:48 Asia/Kolkata | Progress | Consolidated project goals and execution order
- Checkpoint: C005, C008, C009, C010, C011
- Observed result: Reconciled finance-project tasks and related folder tasks into one investing-and-trading outcome, a prioritized execution sequence, and explicit coverage, saved-result, scheduling, education, and publication gaps. The patent and resume-skill tasks were identified as unrelated to fin-AAI.
- Evidence: `docs/CONSOLIDATED_GOALS.md`; project tasks “Assess investing and trading status,” “Fin-AAI Technical Overview,” and “Run and push to new repo”; related daily-course task; repository and this project's existing history.
- Follow-up: Establish a fresh production baseline, save and inspect the first company review, evaluate a frozen trading rule, and expand Nifty 500 evidence in batches.

### E0026 | 2026-09-24 11:12 Asia/Kolkata | Progress | Weekday research and evaluation automation scheduled
- Checkpoint: C003, C008, C009, C010
- Observed result: A local, idempotent runner now has an active Codex heartbeat for weekdays at 8:30 AM and 5:00 PM Asia/Kolkata. The pre-market path refreshes official membership and prior-session closes, screens the 500-company universe and freezes prospective baseline forecasts. The post-market path refreshes completed closes and notices, scores forecasts by session, and records the existing 10-symbol historical strategy gate. Model calls are bounded and require a separate local Groq configuration. Neither path places orders or changes the Momentum paper ledger.
- Evidence: src/stock_research/daily_automation.py; scripts/run_daily_finance.py; scripts/evaluate_finance_daily.mjs; docs/FINANCE_AUTOMATION.md; active app automation fin-aai-pre-market-research. The full Python suite passed 69 tests. At 11:05–11:07 IST, manual calls correctly abstained as after the open or before a completed close. The read-only trading evaluator ran and still returned not eligible: 19 aggregate holdout trades versus 30 required, with -0.364% mean strategy return. The combined recurrence was checked to yield only weekday 08:30 and 17:00 on the host's India Standard Time zone.
- Follow-up: Observe the first full scheduled cycle, inspect source coverage and saved outputs, and resolve any provider configuration or partial-run errors. The hosted Site's own finance scheduler and the authenticated paper-ledger advance remain separate work.
### E0027 | 2026-09-26 Asia/Kolkata | Result | Root repository committed and local automation verified
- Checkpoint: C003, C008, C009, C010
- Observed result: Root commit `90f5d9c` contains the finance source, tests, evidence fixtures, migrations, scheduler, and secret-safe verifier; follow-up commit `f969a57` repairs the trading workstream's runtime import. Windows Task Scheduler contains both `fin-AAI API agents pre-market` and `fin-AAI API agents post-market` in Ready state. The 2026-09-26 pre-market attempt produced an inspectable `exchange_closed` report. The full Python suite passed 77 tests; investing and trading JavaScript suites passed 21 tests total.
- Evidence: `scripts/verify_finance_system.py`; `output/finance-system-verification.json`; `output/finance-automation-2026-09-26-pre.json`; `git log --oneline`; scheduler query output.
- Limitations: The root commit has not been pushed because the remote push requires explicit approval for exporting the source to `origin/main`. Provider variables are missing, so specialist model calls remain `configuration_required`; the latest full market run had 2 verified, 4 stale, 4 blocked, and 490 missing evidence across 500 identities. No broker or real-money execution is connected.
- Follow-up: Approve the exact remote push if desired; configure a caller-owned provider; complete a market-day pre/post cycle; improve evidence coverage; then collect paper results before any broker decision.

### E0028 | 2026-09-26 Asia/Kolkata | Result | Hosted Momentum test suite verified
- Checkpoint: C007, C008
- Observed result: The nested Momentum production build completed successfully and its full application suite passed 40 tests, including finance route rendering, responsive dashboard states, evidence fallback, paper-ledger controls, promotion gates, and API route coverage.
- Evidence: `npm test` in `momentum-site`; build output listed `/finance`, `/api/finance`, `/api/finance/backtest`, `/api/finance/research`, `/api/finance/paper`, and `/api/finance/digest` routes.
- Limitation: This validates the local source and build, not a fresh production deployment or provider-backed model call. The currently deployed Site remains a separate managed checkout.

### E0029 | 2026-09-26 Asia/Kolkata | Result | Ten-company deterministic coverage run saved
- Checkpoint: C001, C003, C008, C009
- Observed result: The reproducible pilot batch covered all 10 configured companies at the 2026-07-18 as-of date. Eight companies passed deterministic readiness; ICICI Bank and NTPC were correctly blocked because their latest accepted annual periods lacked matching annual reports. The result remains `ready: false` for the full batch, so no claim of universal readiness is made.
- Evidence: `output/pilot-coverage.json`; database `output/pilot-coverage.db`; command `weekly-universe --fixtures-root tests/fixtures --universe config/test_universe.csv --window-start 2026-07-07 --as-of 2026-07-18`.
- Follow-up: Acquire and validate the missing annual reports, then rerun the same batch with a current as-of date. This fixture run does not prove live market freshness.

### E0030 | 2026-09-26 Asia/Kolkata | Result | Current official refresh completed for the ten pilot universe
- Checkpoint: C001, C003, C005, C007, C008, C009
- Observed result: An official-source refresh through 2026-09-25 updated 499 of 500 discovery identities in a copied seed. The current-date ten-company pipeline then completed with all 10 pilot companies ready and 0 blocked, including the previously missing ICICI Bank and NTPC annual-report evidence. ITC's current evidence review records 20 accepted financial facts, 14 accepted documents, no governance flags, a latest official close of INR 269 on 2026-09-25, and a deterministic P/E calculation of 16.62.
- Evidence: `output/finance-seed-refresh.json`; `output/current-universe.json`; `output/current-universe.db`; `output/itc-current-evidence.md`.
- Limitation: The ITC report is explicitly `provider_required` and issues no recommendation because no caller-owned model provider is configured. The broad 500-company refresh is discovery pricing only; full financial evidence remains limited to the ten pilot profiles.
- Follow-up: Configure a provider for cited synthesis, then run the same frozen current evidence packet. Expand source-backed financial coverage beyond the pilot set and collect forward paper results before any capital decision.

### E0031 | 2026-09-26 Asia/Kolkata | Result | Momentum version 45 privately deployed with current discovery prices
- Checkpoint: C007, C009, C010
- Observed result: The latest private Site source was reconciled at `c6f132a281065ee7ca9015a8194c6ccd215cda1d`, with the current official discovery seed through 2026-09-25 (499 refreshed symbols). The production build passed 40 application tests locally. Sites saved version 45 and deployment `appgdep_6ab79f380fd88191b7feb5495fbef398` completed with `succeeded`; the owner-only live URL remains https://momentum-os.rajavreddy-g.chatgpt.site.
- Evidence: Sites `get_site` reports `latest_version_number: 45`, `access_mode: custom`, and the succeeded deployment URL; local `npm test` reported 40/40 passing.
- Limitation: This refresh updates discovery prices and volumes only. The ten pilot financial profiles are current and ready in the local official refresh, but the broad 500-company universe is not fully researched. Model provider configuration, paper-trading proof, and broker integration remain open.

### E0032 | 2026-09-26 Asia/Kolkata | Progress | Local provider setup made executable without exposing keys
- Checkpoint: C005, C010
- Observed result: Added `scripts/configure_research_provider.ps1`, which securely prompts for an OpenAI-compatible base URL, model, and hidden API key, stores only current-user environment variables, and never writes secrets to the repository or reports. PowerShell syntax validation passed.
- Evidence: commit `d7df42d`; `docs/API_AGENT_SETUP.md`; parser output `PowerShell syntax OK`.
- Limitation: No provider key is present yet, so no live model call has been made. The helper requires the owner to run it with their chosen provider credentials.

### E0033 | 2026-09-26 Asia/Kolkata | Result | Fresh trading promotion gate remains closed
- Checkpoint: C008
- Observed result: The current ten-symbol evaluator completed through 2026-09-25 with 19 aggregate holdout trades, mean strategy return -0.353%, mean buy-and-hold benchmark -10.470%, and mean excess return +10.117%. The promotion gate remains `not_eligible` because at least 30 aggregate holdout trades are required before review. No order was authorized.
- Evidence: `output/trading-evaluation-2026-09-26.json`; `scripts/evaluate_finance_daily.mjs`.
- Follow-up: Keep the strategy out of real capital, freeze any revised rule before testing, and collect forward paper trades separately.

### E0034 | 2026-09-26 Asia/Kolkata | Deliverable | Practical 30-day finance and ML course added
- Checkpoint: C011
- Observed result: Added a 30-day, 30-minute course covering market data, investing evidence, valuation, governance, trading controls, ML discipline, agents, operations, news, paper trading and a capstone decision memo. Every exercise points to an inspectable fin-AAI artifact.
- Evidence: `docs/FINANCE_ML_COURSE.md`; commit `2c74b60`.
- Limitation: Completing the exercises and evaluating personal learning still requires the owner to work through the schedule.

### E0035 | 2026-09-26 Asia/Kolkata | Artifact | Portable root repository bundle created
- Checkpoint: C010
- Observed result: The complete verified local root history is available as `output/fin-AAI-local.bundle` with SHA-256 `2C4911B283BDFA98B1349DA78A378DB2B8C95546D986DA6E80CF71C634F3BC4C`. The root working tree remains clean; the configured GitHub remote still points to the original first commit because push authorization is pending.
- Evidence: `Get-FileHash output/fin-AAI-local.bundle -Algorithm SHA256`; `git status --short`; `git log --oneline`.

### E0036 | 2026-09-26 Asia/Kolkata | Result | Full cross-layer audit is reproducible
- Checkpoint: C003, C007, C008, C010
- Observed result: `python scripts/verify_finance_system.py --full` completed with a clean root tree, Python tests passing, all four investing/trading workstream suites passing, and the Momentum build/application suite passing 40 tests. The report also records both Ready scheduler tasks, provider-variable presence, the remote commit, and the latest agent report without exposing secrets.
- Evidence: `output/finance-system-full-verification.json`; commit `ef983f1`.
- Limitation: A green audit proves implementation behavior and current operations; it does not prove provider-backed recommendations or profitability. Those remain explicit gates.

### E0037 | 2026-09-26 Asia/Kolkata | Fix | Automation reports now separate paper trading explicitly
- Checkpoint: C008, C010
- Observed result: Every newly generated pre/post report now includes `paperTrading.status: separate_momentum_ledger`, `ordersCreated: 0`, and a plain-language boundary stating that the local scheduler never creates or advances paper orders. An isolated weekend run verified the field in the generated JSON.
- Evidence: `scripts/run_finance_agents.py`; `output/finance-automation-2026-09-26-pre.json`; commit `67775bb`.

### E0038 | 2026-09-26 Asia/Kolkata | Test | Provider HTTP adapter smoke-tested locally
- Checkpoint: C005
- Observed result: Added a local HTTP server test covering the OpenAI-compatible adapter's `/chat/completions` path, bearer authentication, model payload, completion-token cap, and JSON response parsing. The focused test passed 4/4; the full Python suite also passed after the change.
- Evidence: `tests/test_api_agent_config.py`; commit `60468bf`.
- Limitation: This validates the adapter contract only. It is not a live provider call until the owner configures a real provider key.

### E0039 | 2026-09-26 Asia/Kolkata | Result | README and full audit now point to the same clean source
- Checkpoint: C003, C005, C007, C010
- Observed result: The root README now documents the one-command full audit, secure provider setup, and visible report paths. The regenerated full audit points to commit `3e9161e`, reports a clean tree, Python tests passing, all workstream tests passing, and the Momentum 40-test suite passing.
- Evidence: `README.md`; `output/finance-system-full-verification.json`.

### E0040 | 2026-09-26 Asia/Kolkata | Result | Visible acceptance record and current full audit
- Checkpoint: C003, C005, C007, C010
- Observed result: Added `docs/REAL_WORK_STATUS.md` as a visible acceptance record. The current full audit at commit `9a9c3ac` reports a clean tree, 78 Python tests passing, investing/trading workstream suites passing, Momentum 40-test suite passing, and both scheduler tasks registered.
- Evidence: `docs/REAL_WORK_STATUS.md`; `output/finance-system-full-verification.json`; commit `9a9c3ac`.
- Limitation: Provider variables remain missing; the system remains research/simulation only and the trading strategy is not promotion-eligible.
- Bundle: `output/fin-AAI-local.bundle` verifies complete with SHA-256 `40348401E2D7DFAD78D007D43B9C364551884FDC18D4966F1BE7A2FB0358D74B`.

### E0041 | 2026-09-26 Asia/Kolkata | Research | Fixed-protocol walk-forward evidence
- Checkpoint: C007, C010
- Observed result: Added `scripts/evaluate_finance_walkforward.mjs` with a fixed 315-bar rolling window, 63-bar step, unchanged strategy settings, and the existing 70/30 chronological holdout. The report covers 150 windows and 141 holdout trades; 26 windows were positive and 60 beat same-stock buy-and-hold.
- Evidence: `output/finance-walkforward-2026-09-26.json`; commit `8ddbace`.
- Decision: This is additional evidence, not promotion. The positive-window rate and benchmark comparison are not strong enough to authorize capital, and forward paper trading is still required.

### E0042 | 2026-09-26 Asia/Kolkata | Verification | Walk-forward is part of the full audit
- Checkpoint: C007, C010
- Observed result: Updated `scripts/verify_finance_system.py` so `--full` executes `scripts/evaluate_finance_walkforward.mjs` and records its pass/fail output. The audit now proves the rolling evaluation is runnable alongside the 78 Python, 21 workstream, and 40 Site tests.
- Evidence: `output/finance-system-full-verification.json`; commit `e39efc3`.

### E0043 | 2026-09-26 Asia/Kolkata | Site | Walk-forward evidence published visibly
- Checkpoint: C003, C007, C010
- Observed result: The Trading Lab now shows the fixed-protocol walk-forward summary and keeps the strategy visibly unpromoted. Momentum OS version 46 is active in production; deployment `appgdep_6ab7aed196308191b74d64b6bdf3e804` succeeded from Site source commit `b62645f6279bfbb3c16ef5c22a952b9fe0e3fe56`.
- Evidence: `https://momentum-os.rajavreddy-g.chatgpt.site`; Site version 46; `output/finance-walkforward-2026-09-26.json`.

### E0044 | 2026-09-26 Asia/Kolkata | Site fix | Planner saves survive navigation
- Checkpoint: C003, C010
- Observed result: Added `keepalive: true` only to the debounced `/api/planner-state` PUT request. Momentum Site tests passed 40/40, and Site version 47 deployed successfully from commit `7a9544e2b156aceca984f646aa615bb084d2bc32`.
- Evidence: `https://momentum-os.rajavreddy-g.chatgpt.site`; deployment `appgdep_6ab7b0de748081918525da4f90cda8e9`; version 47.
- Limitation: Production logs should be rechecked after a real navigation/save to confirm the browser cancellation is resolved.
