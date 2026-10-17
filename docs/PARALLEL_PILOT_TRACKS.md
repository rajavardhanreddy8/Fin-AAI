# Parallel development tracks

## Current work — 2026-10-17

The news/evidence milestone and reusable next assignments are in [NEWS_INTELLIGENCE_TRACKS.md](NEWS_INTELLIGENCE_TRACKS.md). The current three tracks are collection/provenance, evidence relationships/impact, and independent verification/paper operation. [NEWS_OPERATIONS_STATUS.md](NEWS_OPERATIONS_STATUS.md) records the latest local data and readiness evidence. The dated sections below preserve earlier pilot milestones; their data counts and provider status are historical.

The first real news batch contains 20 general PIB releases. Its local relationship database has no sourced impact links or historical analog outcomes yet. The price archive currently has 736 valid session entries while the merged dataset admits 735, requiring reconciliation before new training. Forward paper still has zero observed bars/trades. These are the immediate gates alongside provider/budget readiness.

## Shared goal

Deliver a measured NIFTYBEES pilot with reusable market evidence, a correct shared
simulation engine, and API-powered Nova/RL/Jev decisions. First integrate and
verify the development foundation; then compare four variants and run genuine
forward paper sessions. Real trading requires qualification and explicit
activation. A development agent finishing its files does not certify trading
readiness or profitability.

Three development agents were dispatched on 2026-10-07. Codex assists with
development; the deployed coordinator and decisions use provider APIs.

## First milestone results

| Track | Verified result | Remaining work |
| --- | --- | --- |
| Data/isolation | 34,425 audited bars from 459 complete regular sessions; 460 raw snapshots have S3 receipts; 13 focused checks pass. | Remaining history, calendars/special sessions, corporate actions and legacy cloud credential cleanup. |
| Engine/RL | Corrected rules-only execution, risk/cost accounting and matched RL rewards; 12 focused checks pass. | Verified execution assumptions, bars-aware exploratory training and qualification verifier. |
| API/paper | Nova transport, typed Jev Decisions transport, bounded coordinator, usage reservations, frozen-RL forward replay, atomic collector-to-paper handoff and candidate-review output; 17 provider/paper, 18 engine and 12 archive/collector offline checks pass. A read-only AWS check verified Nova Lite catalogue and IAM-policy access in `ap-southeast-2`. | OpenRouter credentials and exact Jev snapshot; dated pricing/FX/final billing reconciliation; bounded provider smoke; and an unattended collector credential design before scheduling prospective sessions. |

Root verified the shared CLI on the cached 2026-10-01 session: 53 decisions,
zero completed trades, historical-replay provenance and an unqualified result.
This is an integration check, not a strategy evaluation. Provider status exposes
configuration/evidence gaps without invoking models or returning secret values.

## Progress review and next assignments — 2026-10-08

The three development agents have finished their turns; none is currently
running. Current focused checks: 13 archive/collector + 18 engine + 15 API/paper
= 46 passing. Local dataset hash and 459-session coverage still match. The
forward journal has one start record but zero bars/trades; this is not an active
automated paper service. Today did not recheck remote AWS resources or invoke
provider APIs.

### `data_isolation`: complete and admit the evidence

> Resume only uncached dates using a fresh local Breeze session, preserving
> existing raw files and upload receipts. Reconcile closure/special-session
> dates before declaring missing trading sessions; quarantine invalid data.
> Finish calendar, timestamp and corporate-action checks. Deliver the unchanged
> manifest-admission interface plus a fresh completed-bar handoff for the paper
> runner; keep broker credentials local. Report all residual gaps and prepare
> legacy cloud cleanup for review rather than deleting resources implicitly.

**Done when:** coverage and exclusions are defensible, admitted files reproduce
their hashes, and fresh observed bars reach the runner without broker secrets.
**Owner input:** fresh daily Breeze session through the secure local prompt.

### `engine_rl`: measure the policy and preserve the evaluation

> Use the manifest-verified dataset and existing bars-aware training/comparison
> helpers. Investigate the documented no-trade RL candidate using training and
> validation evidence only; preserve failed runs and the already observed
> holdout. Integrate exact cached Jev/RL+Jev decisions with model/version/cost
> lineage from the API track. Persist candidates, comparison hashes and a
> report separating trading costs from model/infrastructure expenses. Verify
> effective fees and loss-gate evidence; keep insufficient evidence unqualified.
> Any strategy selection following an observed holdout needs new untouched data.

**Done when:** four comparable variants have auditable evidence and the report
explains eligibility without assuming RL is better. Today's reproduced fixed
rule: 43 holdout trades, INR250.11 simulated loss, 5.1548% drawdown under declared
unverified costs. The old report's RL candidate took zero trades; no persisted
candidate/comparison was found in the default pilot database this review.
**Owner input:** actual ICICI brokerage plan/tariff evidence.

### `api_paper`: prove provider calls and connect prospective operation

> Select fin-aai AWS credentials and securely configure OpenRouter. Validate
> current service access, exact Jev snapshot, pricing/FX and daily billing in
> the existing budget-file format. Perform bounded Nova/Jev smoke calls only
> within verified limits, preserving request lineage and usage. Wire active
> frozen RL recommendations into the provider runner, connect fresh-bar
> collection, and schedule prospective paper operation, after-close candidate
> generation and weekly review. Validate observed timing against the current
> one-second assumption; late decisions must abstain and deterministic exits
> must survive outages/budget stops. No policy promotion or live activation.

**Done when:** one complete prospective session has admitted observations,
provider decisions and a rebuildable journal; recurring operation and cost
reconciliation are evidenced. The later 30-session qualification is separate.
**Owner input:** OpenRouter key entered locally, plus its exact dated Jev snapshot,
FX and billing evidence. AWS sign-in is currently available through the local
`fin-aai` profile, but it does not replace those inputs.

## Track 1 — Data and isolation

**Goal:** An audited, resumable data archive that subsequent experiments can
reuse without repeating successful downloads or exposing broker credentials.

**Owner:** `data_isolation`. Checkpoint C012.

**Files:** Breeze collector/archive helpers, local ingestion scripts, their
tests, `output/market-data/`, and `docs/PILOT_DATA_STATUS.md`.

**Development prompt:**

> Inspect the existing collection state and processes before starting work.
> Reuse the NIFBEE/NIFTYBEES archive and restricted raw-upload role. Audit cached
> evidence, materialize aggregate CSV and dataset manifest, verify raw/CSV hashes
> and uploaded versions, and distinguish never-fetched dates, exchange closures,
> provider gaps and malformed bars. Preserve original responses and explicit
> exclusions. Reconcile official calendars, instrument identity and corporate
> actions as far as sources permit. Resume pending uploads only with existing
> authorized access. Do not duplicate ingestion, invent bars, expose credentials,
> delete legacy resources or claim complete isolation without evidence. Leave
> missing access and fee/calendar evidence as precise gaps. Deliver a reproducible
> status report and meaningful collector/cache checks.

**First acceptance:** Aggregate cached dataset and manifest exist; hashes and
coverage are verified; retries do not redownload successful records or skip
never-fetched days; invalid sessions cannot silently enter evaluation.

## Track 2 — Trading engine and RL

**Goal:** Reproducible execution and learning with accurate accounting and
qualification that cannot confuse decisions, replays or assumptions with evidence.

**Owner:** `engine_rl`. Checkpoints C013 and the engine portion of C015–C016.

**Files:** `intraday_pilot.py`, its tests, and `docs/PILOT_ENGINE_STATUS.md`.

**Development prompt:**

> Correct the existing shared engine while preserving CLI compatibility. Keep
> the frozen breakout/VWAP rule and all agreed risk limits. Implement true ATR,
> causally timed fills, stop/target handling, whole-unit sizing, trading costs,
> daily-loss entry blocking, latched drawdown pause, liquidation and restart
> state. Declare bar/fill/slippage assumptions and reject stale or incomplete
> evidence. Make rules-only independent of Q-policy. Train seeded tabular Q
> candidates with no deployed exploration; attribute rewards only to unchanged
> executed RL actions and keep active policies unchanged. Persist completed
> trades, sessions and terminal/state evidence. Require the agreed holdout and
> genuine forward-paper gates; missing cost/model/comparison evidence keeps
> qualification closed. Test chronology, risk, reward and recovery behavior.
> Do not add live broker execution or activation.

**First acceptance:** Deterministic baseline and risk/reward tests pass; costs and
assumptions are explicit; completed trades are counted separately; historical
replays cannot qualify as forward paper activity.

## Track 3 — API agents and paper operations

**Goal:** Nova/Jev adapters, spending controls and an auditable paper workflow
that integrates with the engine and handles unavailable providers safely.

**Owner:** `api_paper`. Checkpoints C014 and the runtime portion of C016.

**Files:** `pilot_agents.py`, `run_intraday_paper.py`, provider/runtime tests,
and `docs/PILOT_API_STATUS.md`.

**Development prompt:**

> Reuse existing provider code where it fits. Integrate Nova Lite through
> Bedrock and Jev through its documented OpenRouter integration; configure and
> record the exact resolved model identity. Validate structured decisions and
> keep coordinator tools bounded. Persist prompts/input hashes, decisions,
> overrides, usage, latency and failures. Enforce the separate Jev monthly cap
> and verified AWS spending envelopes; reserve capacity for reconciliation and
> exits when entries/training are stopped. Missing cost/rate/access evidence
> must remain explicit. Build a paper runner with restart/idempotency and stale
> data guards using the shared engine. Never relabel historical replay as
> forward paper, promote candidates silently, expose credentials, use Codex as
> the deployed model, place orders or deploy cloud resources. Verify with
> mocked/offline checks; attempt a bounded provider smoke test only if existing
> access and budget evidence support it.

**First acceptance:** Provider contracts and budget/recovery checks pass;
configured model IDs and access gaps are inspectable; the paper runner handles
missing credentials/data without creating trades or a false success report.

## Shared interfaces and integration

- Dataset: `at,open,high,low,close,volume`, aware IST bar-start timestamps plus
  provenance, exclusion and quality manifests. Decisions become available only
  after bar completion.
- Model boundary: `decide(evidence: dict, rl_action: str | None) -> str`, strictly
  BUY, HOLD, SELL or ABSTAIN. The engine retains risk and execution authority.
- Engine: Preserve existing replay/transition compatibility. Add optional model
  callback, explicit execution assumptions and persisted initial/final state.
- Root coordinator owns shared CLI wiring, integration review and
  `PROJECT_LOG.md`. Track agents do not edit those shared files.
- Each agent reports changed files, runnable checks, actual results and exact
  remaining evidence gaps before integration.

All tracks develop concurrently. Integration proceeds as:

```text
Audited data + tested engine + tested API/budget contracts
                         ↓
            Reproducible fixed-rule baseline
                         ↓
      Four variants, identical costs, frozen holdout
                         ↓
       Automated forward paper and candidate reviews
                         ↓
      Qualification report → explicit live activation
```

## Shared constraints

NIFTYBEES; completed five-minute bars; ₹5,000; long-only/no leverage/top-ups;
one position; 0.25% planned stop risk; 1% daily entry stop; no entries after
15:00 IST; liquidation begins 15:15; 5% drawdown pause. Risk limits are frozen.
AWS Regional resources remain in `ap-southeast-2`; no new cloud deployment in
this development milestone. Use verified spending evidence, not a presumed
$200 grant. Broker credentials remain with the local data collector; legacy
cloud credential/runtime cleanup is still a separate unresolved item.

The full agreed plan and gaps are in [INTRADAY_IMPLEMENTATION.md](INTRADAY_IMPLEMENTATION.md).

Track evidence: [Data](PILOT_DATA_STATUS.md), [Engine/RL](PILOT_ENGINE_STATUS.md),
and [API/paper](PILOT_API_STATUS.md).
