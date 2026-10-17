# Four development tracks and copyable prompts

Prepared 2026-10-17, Asia/Kolkata. This is the current work allocation. It supersedes the earlier three-track ownership split, while retaining the roadmap and release gates in `NEWS_INTELLIGENCE_TRACKS.md`.

## Starting evidence

The latest repository log (E0063) records the optional Firecrawl adapter and 226 passing Python tests. Firecrawl has extracted zero real pages: source permission, API key and current free-only credit readiness remain gaps. The canonical relationship database contains 20 PIB events/20 event nodes, zero claims, links or analog outcomes. These statements are dated evidence, not a new live audit. Forward paper has zero observed bars/trades. The price manifest has 736 valid sessions while the merged dataset admits 735; fix and reverify before new training.

## Allocation and dependencies

| Track | Owns | First concrete result |
| --- | --- | --- |
| 1. Sources and data | Feed/Firecrawl/Breeze collectors, source registries, raw archives, current-data reconciliation | One permitted extracted article plus a reproducible audited price dataset |
| 2. Evidence and scoring agents | Claims, relationship store, three semantic agent roles, versioned context reports | A cited real news -> exposure -> company/sector/index report with explicit unknowns |
| 3. Outcomes and learning | Reaction labels, case matching, chronological experiments, score calibration and RL evaluation | A measured baseline using eligible evidence and completed price outcomes |
| 4. API platform and paper deployment | Provider access/budgets, private worker packaging, recovery, monitoring, paper-session operations | A reviewable deployment package and verified prospective paper rehearsal |

Tracks 1 and 4 can verify data/provider readiness while 2 and 3 build against clearly labelled fixtures. Real graph verification depends on track 1. Real training depends on reconciled prices and eligible historical evidence from tracks 1/2; newly collected news cannot retrospectively become historical decision input. Deployment/paper integration depends on accepted track 2 contracts and track 4 readiness. Prediction results must remain unknown until track 3 has sufficient untouched evidence.

The coordinator owns shared CLI integration, this plan and `PROJECT_LOG.md`. Each track owns its matching tests and its own status report. A shared-file change requires coordination with its owner; do not concurrently edit the same implementation file. Preserve existing function contracts or propose the smallest explicit interface change before editing callers owned by another track.

## Common preamble — include with every prompt

```text
Work in C:\Users\admin\Desktop\fin-AAI with that folder as the writable workspace. If access is unavailable, report the exact missing folder permission; do not create a replacement repository. Read AGENTS.md, news_intelligence.md, docs/NEWS_INTELLIGENCE_TRACKS.md, docs/NEWS_OPERATIONS_STATUS.md and the code you will change. Treat old status counts as dated and inspect current artifacts before claiming readiness.

Use Sol low for planning when needed and Luna low for implementation/independent verification. Effort above high requires the owner's permission. Use applicable installed skills, preserve unrelated Git changes, reuse current helpers, and use apply_patch for edits. Do not expose keys, broker sessions or private databases. Finish authorized local implementation and meaningful checks even if provider configuration is missing; report the exact remaining gap. Paid calls require current verified budget evidence. This prompt prepares work; it does not authorize new subscriptions, cloud provisioning, policy promotion, broker orders or live activation.

Keep immutable evidence and real availability times. Clearly distinguish fixtures, real saved evidence, provider smoke tests and prospective paper results. End with changed files, test results, actual evidence coverage, blockers and the next gate. Write your own track status report; the coordinator reconciles shared project history.
```

## Track 1 prompt — sources and reliable data

```text
Goal: make reusable, permitted news and price evidence available to the other tracks.

Own collectors, source registries, scripts/run_market_ingest.py, archive reconciliation and their tests. First inspect the existing Firecrawl adapter and docs/FIRECRAWL_INGESTION.md; do not reimplement it. Verify the exact source's extraction/retention rights and provider free-only readiness. If the key is missing, provide the secure configuration step without asking for its value in chat. When readiness is established, extract one permitted real article within existing request limits, archive it and import it twice into output/market-news/market-relationships.db. Prove old headline records remain unchanged and the extracted body appears only after its completion time.

Reconcile the 735/736-session price discrepancy, including 2023-11-12, by producing a new audited dataset/manifest. Preserve previously frozen comparison inputs and hashes. Report remaining missing/invalid sessions and cost/calendar/action gaps.

Then expand permitted issuer, exchange, Indian-policy and global-policy coverage incrementally through existing adapters. Track source failures, observation latency, revisions and company mapping coverage; do not fabricate publication dates or entities. Keep Breeze credentials on the local device; upload only permitted data through the existing isolated handoff.

Accept when real source provenance, repeat-import idempotency, extraction cutoff, refreshed-feed/retry behavior and current dataset verification are demonstrated. If live extraction is blocked, finish all offline work and name the source/access/credit gap. Write docs/NEWS_TRACK1_STATUS.md. Do not edit the relationship schema or provider transports owned by other tracks.
```

## Track 2 prompt — evidence graph and scoring agents

```text
Goal: turn admitted articles into inspectable answers about trust, exposure and historical support.

Own context_store.py, market_context.py, market_context_agents.py, their context/relationship/annotation commands and matching tests. Reuse the provider interface in pilot_agents.py; track 4 owns that transport/budget module. Agree the input/output contracts with track 3 before adding a historical-case matcher.

Implement three bounded API roles: Evidence Assessment, Exposure/Impact and Historical Comparison. Extract claims with exact source spans; record authority, corroboration, contradiction and unknowns separately. Propose directed company/sector/index exposure paths only with evidence, knowledge time, mechanism and horizon. Use sourced dated constituent weights for index coverage; keep measured index contribution separate from sentiment.

Preserve the eight approved category scores, confidence, freshness, missingness and coverage. Version prompts/model outputs and persist annotation completion times. Keep overall score aggregation an explicitly unvalidated baseline until track 3 supplies accepted calibration evidence. The historical role retrieves only earlier completed cases and reports sample counts/distributions; it must abstain when no eligible match exists. Conversational memory cannot substitute for cutoff-filtered evidence.

Accept with one reviewed real source-to-impact example if source access permits, citations supporting each link, and checks for unsupported links, corrections, double counting, prompt injection and future evidence. Use labelled fixtures while inputs are unavailable and report that limitation. Keep outputs in shadow research. Write docs/NEWS_TRACK2_STATUS.md; do not deploy or alter trade rules.
```

## Track 3 prompt — outcomes, experiments and learning

```text
Goal: measure whether the news/relationship scores add predictive or trading value.

Own the outcome-label dataset, matching/calibration logic, experiment reports and their tests. Reuse existing investigation/candidate-review helpers; coordinate changes to market_context.py with track 2, which owns it. Reuse the intraday engine without changing frozen trading rules.

Join events at their actual available time to later completed 5/30/60-minute and next-session price windows. Define trading-session boundaries explicitly; do not silently label missing bars. Record raw and market/sector-relative returns, adverse excursion, spread/cost assumptions, regime and confounding events. Include gains, losses, no reaction and eligible no-trade cases.

Historical articles downloaded now are not evidence available to the old bot. Keep exploratory reconstructed datasets separate from prospective decision evidence, and disclose historical model-memory limits. Train/select on chronological training/validation ranges; isolate syndicated stories and overlapping outcome windows, purge labels crossing boundaries, freeze and do not recycle holdouts. Start with simple baselines and calibrated lightweight models, then measure any benefit of category weighting or historical-case matching. Insufficient sample size must produce insufficient_evidence, not a successful model.

Compare rules, Jev, RL and combined variants with identical execution assumptions; evaluate news context as an additional controlled comparison. Report trading costs and operating/model costs separately. RL learns policy only; attribute forward rewards only to RL actions executed unchanged, train candidates separately, and never auto-promote.

Accept with reproducible split/data/prompt/policy hashes, saved failed experiments, error/calibration/coverage metrics and uncertainty. Write docs/NEWS_TRACK3_STATUS.md. Do not train on unresolved price artifacts or claim live qualification from repeated historical runs.
```

## Track 4 prompt — provider APIs, private deployment and paper operation

```text
Goal: prepare reliable, budgeted continuous execution of the accepted pipeline and verify paper operation.

Own pilot_agents.py provider/budget transports, paper-session worker/operation scripts, deployment packaging, infra files and their tests. Track 2 owns semantic prompts, relationships and context modules; consume their agreed contracts. Read applicable AWS skills before AWS work.

Recheck selected-Region ap-southeast-2 access, AWS project plan/remaining credits/expiry, current model runtime availability, quotas, pricing/FX and billing evidence. Catalogue visibility is not a successful invocation. Reuse IAM service roles and safe secret storage. Reconcile provider usage locally and preserve spending reserve for recovery/exits; alerts alone are not a hard cap. Verify existing pilot monthly ceilings rather than invent a new budget.

Prepare one private worker to run the three semantic roles, backed by durable event/job state and the existing data handoff. Keep SQLite on one durable writer host initially; do not put the sole database on ephemeral agent-runtime storage. Evaluate AgentCore hosting only after selected-Region availability, storage, credentials and total cost are established. AWS is the existing path; GCP remains an optional separately budgeted proposal, not a second deployment target for this task.

Package a reviewable deployment with IAM scope, encrypted backups/restore, bounded jobs, overlap protection, retries, idempotency, heartbeat/latency/error monitoring and rollback. Finish local implementation first; resource creation or scheduler activation needs an explicit deployment instruction.

Accept with provider-failure/budget/stale-data/restart tests, a fresh-bar prospective paper rehearsal and evidence that broker credentials/orders remain inaccessible to news agents. Report prepared versus deployed versus operating separately. Write docs/NEWS_TRACK4_STATUS.md. Preserve the existing holdout/forward/live qualification gates and require explicit user activation for live execution.
```

## Integration checklist for the coordinator

1. Verify each track's source files, outputs and claimed checks; inspect evidence gaps before merging contracts.
2. Keep one canonical relationship database and immutable snapshot archive. Avoid overlapping collector/paper consumers and unmanaged SQLite writers.
3. Trace one real event through collection, cited claims, directed relationships, cutoff-filtered history and a persisted shadow report. Test restart and late revision behavior.
4. Use prospective inputs for paper operation; only promote learned weights/policies after independent untouched evaluation and the existing qualification gates.
5. Update the shared log and give the owner a concrete deployment review. No completion date substitutes for evidence.
