# Intraday pilot: implementation and evidence

Updated 2026-10-07 Asia/Kolkata. This is the NIFTYBEES pilot; the existing Momentum company-research workflow remains separate.

## Accepted goal

Build API-powered agents: Amazon Nova Lite coordinator, a CPU Q-learning policy, and Jev through OpenRouter, followed by deterministic risk controls. Compare the same strategy with rules alone, Jev, RL, and RL plus Jev. Current operation uses Breeze **only for local data collection**; AWS receives candle evidence for backtesting and paper trading. Live execution is a later release requiring qualification and explicit activation.

Pilot defaults: completed five-minute bars, long-only, no leverage, ₹5,000 capital, no top-ups, 0.25% planned stop risk per trade, one position, 1% daily entry stop, 5% drawdown pause. Jev budget is ₹300/month. On 2026-10-07, the AWS billing API verified FREE/ACTIVE, $117.44 remaining credit and expiry 2027-04-02 13:25:02 UTC (`reference/aws-plan.json`). Bedrock/service eligibility still requires verification; $200 available credit is not established. Local provider reservations now enforce configured spending envelopes, but verified pricing, FX, daily billing imports and actual provider access remain required before use.

Three development tracks and their copy-ready prompts are in [PARALLEL_PILOT_TRACKS.md](PARALLEL_PILOT_TRACKS.md). Their first milestones are recorded below; full evaluation and scheduled operation remain open.

## Next phases and acceptance checks

| Phase | Work | Evidence required to finish |
| --- | --- | --- |
| 1. Reusable data | Cache up to three years of available NIFBEE history, reconcile calendars and instrument identity, audit every session. | Raw hashes, S3 versions, normalized CSV hashes, explicit gaps, corporate-action review; no silent forward filling. |
| 2. Correct shared engine | Finish next-bar execution, ATR(14), stop/target handling, cash and position accounting, costs, persistent loss pauses and restart recovery. | Reproducible fixed-rule baseline; tests for leakage, risk enforcement, gaps, stale bars, fills, timeouts and restart behavior. |
| 3. API agents and learning | Verify Bedrock/Jev versions and structured decisions; implement seeded training and bounded tools; persist costs and decision lineage. | Real API smoke tests, fail-closed model behavior, RL/Jev/execution recorded separately, no overridden reward attribution, budget reserve protecting open positions. |
| 4. Four-way comparison | Split audited history chronologically 60/20/20; freeze rules, prompts and policies before untouched holdout. | All four variants share data and costs; at least 100 holdout trades, positive expectancy after trading costs, drawdown below 5%; RL improves net results over Jev-only. Report compute/model expenses separately. |
| 5. Automated forward paper | Run completed-bar collection and paper sessions; save transitions; train candidates after close and evaluate weekly on subsequent untouched data. | At least 30 **completed forward paper trades across 30 sessions**, no unresolved execution defects; candidates cannot silently replace active policies. |
| 6. Later live release | Recheck broker/static-IP/protection requirements, reconcile state, present qualification for activation. | All stricter existing gates plus the pilot gates, one-time activation; any changed live policy must requalify. Current data-only scope remains in effect. |

## Actual implementation gaps

The 2026-10-07 resource inventory also found the legacy `fin-aai-breeze-collector`
EC2 instance still running at 52.65.11.177 and the previous
`BreezeCollectorSecret-4zDJPaWSgSUd` secret still present. Secret values were not
retrieved during this inventory. The local collector works independently of
these resources, but legacy runtime/credential cleanup is still needed before
claiming the whole AWS project contains no Breeze credentials. Inventory:
`output/market-data/reference/aws-status.json`.

The shared simulation engine now implements true ATR, delayed fills, stop/target handling, fees/slippage assumptions, preentry daily-loss blocking, a latched drawdown pause, completed-trade accounting and corrected RL reward attribution. The CLI fixed-rule baseline has no Q-policy. Twelve focused engine scenarios pass. Actual tariffs, spreads, partial/protective fills, model latency and broker recovery are still unverified; see [PILOT_ENGINE_STATUS.md](PILOT_ENGINE_STATUS.md).

Nova/Jev adapters, bounded coordinator routing, SQLite usage reservations and a restartable fresh-bar paper runner now exist. Offline provider checks do not establish model access. The current CLI runner operates rules-only; provider callbacks can be integrated through its Python API. No scheduled feed, four-way experiment or successful real API invocation was established by this milestone. Qualification remains closed pending a full evidence verifier. Historical replay cannot count as forward paper. See [PILOT_API_STATUS.md](PILOT_API_STATUS.md).

## Data collected and data still needed

| Input | Saved evidence or gap |
| --- | --- |
| Five-minute OHLCV | Aggregate `output/market-data/audited-bars.csv`: 34,425 bars from 459 complete regular sessions, with raw/normalized hashes and S3 receipts. One invalid session excluded; 310 missing manifest entries require closure/special-session/gap classification. Full requested history is incomplete; see [PILOT_DATA_STATUS.md](PILOT_DATA_STATUS.md). |
| Identity | Official Breeze `SecurityMaster.zip` and `reference/sources.json`: NSE ticker NIFTYBEES, Breeze code NIFBEE, ISIN INF204KB14I2. |
| Session calendars | Existing saved 2026 NSE calendar; official base calendar PDFs/text for 2023–2025 under `reference/`. Historical amendments, special Saturday sessions and Muhurat sessions still require reconciliation. |
| Corporate actions | Saved the dated NSE corporate-actions API response for the requested range: zero rows. This is not independent proof of no actions; issuer distributions and adjustment review remain open. Breeze V2 is unadjusted. |
| Trading costs | Saved official ICICI brokerage page and Breeze API reference with hashes. The charges PDF download failed; exact owner's brokerage plan, effective tariffs and ETF applicability remain unverified. Do not invent a flat fee and call it verified. |
| Spread/slippage/fills/latency | Five-minute OHLCV cannot establish actual bid/ask spreads, fills or decision latency. Use declared conservative assumptions and sensitivity tests initially; collect prospective observations in paper mode. |
| Model/infrastructure usage | AWS plan/balance/expiry saved in `reference/aws-plan.json`; local ledger and request audit implemented. Live resolved Jev identity/version, model access, dated pricing/FX and daily billing imports remain needed before model experiments. |

## Reuse and resume

The launcher reuses the owner-restricted, Git-ignored `.env.local` app key/secret and asks for an ephemeral Breeze session. It does not send Breeze credentials to AWS. The upload role can write only `raw/*`; the local archive and manifest remain available if AWS upload fails. Content-addressed S3 keys and version IDs identify the exact uploaded input. Raw files are never replaced by normalized data.

From **Command Prompt**, paste this as one line:

```cmd
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_local_breeze_ingest.ps1 -HistoryFrom "2023-10-09" -HistoryTo "2026-10-06"
```

Rerunning reuses cached snapshots, audits them again and retries pending uploads. Previously recorded empty responses are retained as gaps; the Python CLI's `--retry-missing` explicitly retries them. Missing historical calendars mean weekday collection only, with completeness unverified. The ordinary single-session arguments still work.

After a history run, the manifest is also backed up under the upload role's
`raw/_manifests/` prefix. Its S3 key and version are saved in
`output/market-data/collection-result.json`. CSVs can be regenerated from the
preserved raw snapshots.

Audit a cached date without credentials, Breeze or AWS:

```cmd
python scripts\run_local_breeze_ingest.py --history-from 2026-10-01 --history-to 2026-10-01 --audit-cache
```

Exit code 2 means recorded quality/calendar gaps remain. Valid regular-session CSV contains 75 bar-start timestamps from 09:15 through 15:25 IST; the provider's extra 15:30 endpoint is preserved in raw evidence and excluded from that CSV. Sparse sessions are flagged rather than filled. Cross-checking the provider's candle-label semantics against a second source remains part of final data qualification.

## Sources

- [Official Breeze Python SDK: historical V2 and limitations](https://github.com/Idirect-Tech/Breeze-Python-SDK/blob/main/README.md): 1,000 candle intervals per request; historical data is not corporate-action adjusted.
- [NSE base 2023 calendar](https://nsearchives.nseindia.com/content/circulars/CMTR54757.pdf), [2024](https://nsearchives.nseindia.com/content/circulars/CMTR59722.pdf), [2025](https://nsearchives.nseindia.com/content/circulars/CMTR65587.pdf). Base notices do not prove later amendments are covered.
- [NSE current market timings and holidays](https://www.nseindia.com/resources/exchange-communication-holidays).
- [ICICI Direct brokerage](https://www.icicidirect.com/brokerage) and [official Breeze API reference](https://api.icicidirect.com/breezeapi/documents/index.html). The owner's effective plan still needs confirmation.

The change history and current checkpoints are maintained in [PROJECT_LOG.md](../PROJECT_LOG.md).
