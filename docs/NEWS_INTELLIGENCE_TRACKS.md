# News evidence and market impact: three delivery tracks

Updated 2026-10-17, Asia/Kolkata. This is the implementation direction for the NIFTYBEES research pilot. Deliveries and operational checks are recorded in `PROJECT_LOG.md`; a planned component below is not a claim that it is running.

Current work allocation: [NEWS_FOUR_TRACK_PROMPTS.md](NEWS_FOUR_TRACK_PROMPTS.md) splits the remaining development into collection/data, evidence/scoring agents, outcomes/learning, and provider/deployment/paper operations. It supersedes the earlier three-track ownership split below; the three semantic runtime roles and release gates remain applicable. The latest logged Firecrawl implementation milestone is E0063 (226 tests; zero real extracted pages), so the collector should be reused rather than rebuilt.

## What we are building

For each new story, answer three questions with inspectable evidence:

1. What does it claim, where did it originate, and what supports or contradicts it?
2. Which companies, sectors, economic factors, and indices could it affect, through what exposure, over what horizon?
3. Which earlier comparable events and completed outcomes support that estimate, and where is the evidence insufficient?

The database stores the original evidence, dated relationships, and subsequent outcomes. A report can say “unknown.” Source reputation, whether a claim is supported, model confidence, and the expected market effect are separate fields. A regulatory announcement establishes what the regulator announced; it does not establish that a predicted share-price response will occur.

The runtime agent roles are Evidence Assessment, Exposure/Impact, and Historical Comparison. Their shared coordinator should use the existing budgeted API infrastructure and schema validation. Development uses Sol at low effort for planning and Luna at low effort for implementation and independent checks. These development agents do not become the deployed trading models.

## Current direction and ownership

| Track | Existing foundation | Work in this delivery | Next acceptance gate |
| --- | --- | --- | --- |
| 1. Collection and evidence | Upstox and permitted RSS/Atom adapters, raw hashes, revisions, completed-bar archive, dated-membership parser | Run a bounded public-feed collection; make feed-only operation work; preserve source and actual observation time | Repeated collection adds genuine new observations without losing old raw evidence; failures/coverage visible; real issuer and policy coverage measured |
| 2. Relationships and impact | Eight-category snapshots, sector peer comparisons, investigations, candidate-review calculations | Persist events, sourced claims, dated typed relationships and prior outcome cases in SQLite; provide cutoff-aware reports | A real story can be traced to documented exposure, affected entities and eligible prior cases, or explicit gaps; no future evidence or duplicate effects |
| 3. Verification and paper operations | Budgeted Nova/Jev contracts, paper journal, recoverable handoff, unregistered scheduling script | Recheck current tests/artifacts, import the real batch and test reports, report provider/data gaps | Valid provider/budget evidence, prospective collection and shadow reports survive restart; reports agree with stored evidence |

The first delivery is a locally verified evidence foundation. Automatic model generation of relationship assertions, a continuous service and a trained impact predictor are subsequent gates. The existing news annotator scores eight categories; that alone is not a verified three-role runtime.

## Delivered foundation and local commands

The first bounded collection saved 20 real PIB release entries at `2026-10-16T04:09:18Z`, one immutable feed snapshot, and a resumable checkpoint under `output/market-news/`. The source supplied titles/links but no publication dates or summaries; these remain missing. This is general government coverage, not verified coverage of the Nifty constituents. No real model annotations or inferred company-impact assertions have been generated from this batch.

The SQLite database `output/market-news/market-relationships.db` contains those 20 events and 20 event nodes. Claims, impact relationships and historical outcomes are empty. Reports explicitly keep those answers unknown. Independent checks and the remaining archive/provider gaps are recorded in [NEWS_OPERATIONS_STATUS.md](NEWS_OPERATIONS_STATUS.md).

Run from the repository root with the project Python environment. These two commands inspect saved evidence without a network/model call:

```powershell
python scripts/run_market_relationships.py status --db output/market-news/market-relationships.db
python scripts/run_market_relationships.py report --db output/market-news/market-relationships.db --asof "2026-10-17T00:00:00+05:30"
```

To collect another permitted feed observation, keep the existing output directory/checkpoint and respect the registry's polling interval. The following command makes a public-feed request; importing its result is local and idempotent:

```powershell
python scripts/run_market_ingest.py --feed-registry config/market-news-sources.json --output output/market-news --refresh
python scripts/run_market_relationships.py import output/market-news/market-ingest.json --db output/market-news/market-relationships.db
```

Check collection status before consuming it: `complete` exits 0; `partial` or `failed` exits 2 and retains successful evidence plus explicit gaps. The importer validates event records, but does not turn an incomplete source collection into complete market coverage. A feed-only run requires no Upstox token. The collector is not yet a continuously scheduled service.

## Collection and scraping

Use the least expensive source that carries the needed evidence:

- Exchange disclosures, company investor-relations pages, RBI/SEBI releases and permitted government feeds for primary claims.
- Upstox instrument news for discovery and stock mapping after its read-only Analytics Token is verified.
- Permitted publisher feeds/pages for additional reporting and disagreements.
- Social posts only through allowed access, with author identity, original URL, first observation and deletion/correction history where available. Social popularity is not corroboration.
- Firecrawl or Crawl4AI for permitted pages requiring article extraction or rendering. Neither crawler establishes truth, creates missing historical archives, or grants training rights.

Firecrawl supports Markdown and structured page extraction ([documentation](https://docs.firecrawl.dev/introduction)); Crawl4AI supports controlled browser crawling ([configuration](https://docs.crawl4ai.com/core/browser-crawler-config/)). They are optional collection adapters, not a reason to replace the working feed collector. A bounded feed run can start without another paid service or GPU.

Upstox's documented news endpoint supplies the past **seven days**, with up to 30 instrument keys per request ([News API](https://upstox.com/developer/api-documentation/get-news/)). Five years of news requires separately licensed/permitted archives and honest coverage records. Begin prospective archiving immediately. Preserve observed time: an old article downloaded today cannot be represented as evidence our system possessed years ago.

The source registry should document the publisher's feed/reuse basis, allowed retention and training use, polling interval, and evidence URL. Respect source restrictions and rate limits; do not bypass access controls. Store only permitted content. Scrape once per revision, deduplicate syndicated copies, and keep source failures visible. Reuse the archive/checkpoint with explicit `--refresh` for new observations so the normalizer retains the first observed event time. Resuming a completed checkpoint without refresh is not a fresh poll. Independent archives need observation reconciliation before database import.

Suggested collection cadence is conditional on source limits: price stream continuously during the exchange session; fast news feed every 1–5 minutes where permitted; slower filings/pages every 5–15 minutes; overnight updates at lower frequency. Measure publication-to-observation and observation-to-decision latency. Web polling cannot promise to catch the first seconds of a shock.

## Database and temporal rules

Start with SQLite beside the existing raw archive. Reuse established security identities (prefer ISIN), source IDs and dated index inputs. Do not duplicate the candle history into a new graph database.

```text
Source document / article revision
          -> reported claim or policy
          -> documented company exposure
          -> estimated revenue, cost, credit or risk effect
          -> dated sector / index membership

Prior comparable event -> completed outcome -> historical evidence
```

Links can branch to multiple companies, commodities, countries and macro factors. Company-to-sector membership is a classification, not proof the company caused its whole sector to move. Keep reported claims, documented exposure, estimated effects and observed outcomes distinguishable.

Required controls:

- Immutable IDs and payload hashes; exact repeat imports are idempotent; changed payloads with the same ID reject atomically.
- Publication time, actual observation time, processing availability and relationship knowledge time remain distinct. Preserve unknown publication times.
- Every relationship has typed endpoints, source/claim evidence, knowledge time, effective interval and an impact horizon where relevant.
- A decision at time T may use only events, annotations, relationships and completed historical outcomes known by T. Later corrections and investigations remain new versions.
- A snapshot selects an eligible revision per canonical event. A single shock reaching the same company through several paths must not be counted several times.
- Historical cases retain provenance, horizon, state of the market, comparison method, sample count and uncertainty. Search results or LLM memory are not observed return data.
- Keep actual price contribution and estimated sentiment impact separate. Approximate index contribution uses beginning-of-period constituent weight multiplied by its measured return; missing weights stay missing. Reuse the existing complete dated-weight checks.

## Agent outputs and scoring

| Runtime role | Required output | Must remain unknown without evidence |
| --- | --- | --- |
| Evidence Assessment | Claim text/type, original source, timestamps, novelty, authority, corroboration/contradictions, citations | Truth probability; independence of syndicated reports; unretrievable/deleted content |
| Exposure/Impact | Entity IDs, direct/indirect path, mechanism, direction, horizon, materiality evidence, confidence, affected index weight coverage | Unreported supplier/customer exposure, numerical earnings effect, guaranteed price direction |
| Historical Comparison | Eligible prior case IDs, matching features/regime/horizon, observed return distribution and cost assumptions | Reliable forecast from a small or biased sample; causal attribution |

Use the existing eight categories: company performance, valuation/expectations, sector conditions, governance/policy, domestic economy, global conditions, external risks, and market behaviour. Keep the component vector, confidence, freshness and coverage. A later 0–10 presentation can map a validated directional score to a readable scale; it is not a probability of profit. Missing evidence must not be silently converted into a neutral score.

The existing Nova wrapper supplies bounded annotations. Extending it to structured claims and impact paths requires schema validation, source-span checks, bounded retrieval, usage logging and fail-closed handling. Retrieved text is untrusted data and must not supply instructions or execution authority. A source citation existing is necessary but does not prove it supports the assertion; inspect that relation explicitly.

## What can affect our trading prices

These are candidate explanatory variables, not fixed rules that predict direction.

| Factor family | Data to collect | Trading implication to evaluate |
| --- | --- | --- |
| Expectations and surprise | Earnings/guidance vs contemporaneous consensus, policy decisions vs expectations, revisions | Positive wording can accompany a negative surprise; retain what was expected before publication |
| Company economics | Sales, margins, cash flow, debt/refinancing, orders/cancellations, management, governance and legal events | Materiality depends on company size, exposure, valuation and horizon |
| Sector and supply chain | Input/output prices, customers, suppliers, competition, regulation and industry demand | The same shock can create winners and losers across sectors |
| Macro and global conditions | RBI/Fed communications, inflation/growth, yields, INR, crude, global equities/futures | Transmission through financing costs, currency exposure, demand and risk appetite |
| External shocks | War/sanctions, tariffs, shipping disruptions, weather/water, outages and cyber events | Validate company exposure; do not assign a blanket score to every stock |
| Market structure and positioning | Bid/ask depth, spread, trades/volume, volatility, derivatives positioning, auctions, rebalances and expiry | Price can move without new company news; execution quality and position crowding matter |
| Index and ETF mechanics | Dated constituent weights, heavyweight contributions, breadth, ETF premium/discount and tracking | Distinguish a broad market move from a few large contributors and ETF-specific pricing |
| Timing and prior reaction | First observation, move already made, release calendar, session, liquidity/volatility regime | The remaining opportunity after latency can be different from the initial reaction |

Nifty 50 uses free-float market-capitalisation weights ([Nifty Indices](https://www.niftyindices.com/indices/equity/broad-based-indices/nifty--50)). Our instrument also has its own spread and liquidity; NSE describes why execution impact depends on order size and available liquidity ([impact cost](https://www.nseindia.com/static/products-services/indices-impact-cost)). Fees, slippage and latency affect net returns even if a directional estimate is correct.

For this five-minute pilot, first test novelty/surprise, documented exposure, price/volume reaction, breadth, volatility and tradable spread. Add slower fundamental features as context. End-of-day institutional flow reports cannot be used earlier than their actual release. Five-minute OHLCV cannot reconstruct historical order-book depth.

## Validation and later training

1. Validate source and extraction mechanics: counts, revisions, timestamps, identity mapping, rights/retention, missing coverage and restart behaviour.
2. Build a reviewed sample for each event type. Check claim/citation support, affected entity precision, disagreement labels, category direction and confidence calibration. Do not use model self-confidence as the reference label.
3. Join first-available events with later completed price windows, initially 5/30/60 minutes and next session. Store raw and sector/market-relative returns, adverse excursion, spread/cost assumptions and confounding events. Include winners, losers, no reaction and eligible no-trade cases.
4. Freeze chronological train/validation/holdout boundaries. Keep syndications and overlapping event/outcome windows out of separate folds; remove training labels whose outcomes extend into validation. Train and select only on the training/validation side. Do not recycle previously inspected holdouts.
5. Compare simple baselines and calibrated lightweight models before LLM fine-tuning. Historical retrieval must access only cases/outcomes already available at the decision cutoff. Historical LLM memory remains a limitation; frozen prospective paper evaluation is essential.
6. Run shadow evaluation against the existing rules/Jev/RL comparisons. Measure predictive errors, coverage, abstentions, net expectancy, drawdown and operating cost. Promote context into trade filtering only if subsequent untouched and forward evidence supports it.

RL remains a trading-policy learner. It does not learn article truth, and an overridden RL action must not receive the executed trade's reward. No automatic promotion or live activation is created by the new database.

## Infrastructure and dependencies

GCP and a GPU are not needed for this first milestone. Use the existing AWS project for eventual continuous operation, with application resources restricted to `ap-southeast-2`; start local verification before deployment. SQLite and archived source snapshots suffice until measured concurrent writers/query load justify a database migration.

The 2026-10-17 Bedrock/Google Cloud agent comparison is recorded as a proposal in `../news_intelligence.md`. Prefer reusing the current provider wrapper and one worker for the three bounded intelligence roles, with AgentCore Runtime considered for later managed hosting. Google ADK/managed Agent Runtime remains an alternative requiring its own readiness and budget evidence; no second cloud deployment is selected by this proposal.

Continuous operation still needs verified provider access, current spending evidence, polling/restart monitoring, and a reliable fresh-price handoff. The 2026-10-16 AWS readiness entry records USD108.21 remaining credit and Nova catalogue visibility; that is a dated observation, not proof of working model invocation or a hard spend cap. Jev smoke-test evidence is recorded separately in `PILOT_API_STATUS.md`.

Credentials stay in approved local/environment or service-secret storage, never in article archives, prompts, source control, or chat. Firecrawl credentials and extra cloud services are optional until a selected source needs them. Train on content only after its permitted use and lineage are established.

## Development and deployment phases

Each phase has an evidence gate. A later phase may be prepared in code, but must not be treated as operational until its own gate passes.

| Phase | Development outcome | Deployment outcome | Gate to proceed |
| --- | --- | --- | --- |
| 0. Repair the research inputs | Reconcile the 735/736-session archive discrepancy; preserve frozen evaluation artifacts; verify permitted source terms and source registry entries | None | Rebuilt dataset has a recorded manifest/hash and passes archive verification; source coverage and gaps are saved |
| 1. Expand evidence collection | Add only selected issuer, exchange, policy and global primary sources; preserve raw revisions, first observation and failures | Local scheduled collection only, after restart/retry tests | At least one refreshed real batch per source, no duplicate/revision regression, and a coverage report by issuer/date |
| 2. Build the evidence graph | Add reviewed claims and directed policy/news -> company -> sector -> index links, each with source spans, timing and dated weights | SQLite stays local; encrypted backups are prepared but no public endpoint | A reviewer can trace a real example end-to-end or the report explicitly says unknown; future-leakage and double-counting tests pass |
| 3. Label and validate outcomes | Join eligible events to 5/30/60-minute and next-session outcomes, cost assumptions and regimes; create chronological splits | Batch jobs remain local or on one private AWS worker once inputs/restart handling are proven | Baseline models beat a no-information baseline on untouched validation data, with coverage, calibration and abstention reported |
| 4. Shadow intelligence | Connect the three API roles: Evidence Assessment, Exposure/Impact and Historical Comparison. Their output only filters/reports alongside rules/Jev/RL decisions | Private AWS deployment in `ap-southeast-2`: one worker, private storage, Secrets Manager, monitoring and restart reconciliation | Budget/readiness checks, model-failure handling, fresh timestamps, and paper journal recovery succeed; no decision uses future evidence |
| 5. Forward paper operation | Freeze prompts, policies and score versions; collect prospective evidence and compare rules, Jev, RL and context variants | Scheduled private worker only after a successful manual full-session rehearsal | At least 30 forward paper trades across 30 sessions, positive after-cost expectancy, drawdown below 5%, no unresolved execution defects |
| 6. Live-release review | Produce the qualification report and require a fresh user activation; deterministic risk code remains the only execution authority | Add broker execution only after the user activates it; keep emergency stop/reconciliation independent of model availability | Existing live gates plus 100 holdout trades and demonstrated net improvement over Jev-only if RL/context is included |

Deployment starts in Phase 4, not before. The initial topology is deliberately small: local Breeze data handoff -> private AWS object storage/database -> one private worker -> paper journal/report. There is no public dashboard, public trading API, or automatic live activation. If CI/CD is later added, use a queued pipeline with tests before deployment, scoped service roles and Secrets Manager references; keep application resources in `ap-southeast-2`.

### Immediate ordered backlog

1. Rebuild and verify the 735/736-session price archive discrepancy without overwriting frozen comparisons.
2. Add the next permitted primary source with an explicit reuse/retention record, then collect a refreshed real batch.
3. Curate one real policy/news -> company -> sector -> Nifty relationship chain with citations and dated index weights.
4. Add completed price-outcome labels and run the first chronological baseline evaluation.
5. Verify Bedrock/OpenRouter budget evidence and recovery behavior before any AWS paper-worker deployment.

The first acceptance demonstration is one real source batch imported twice without duplicates, a report before collection that excludes it, and a report after collection showing its claims or honest evidence gaps. A complete real policy-to-company-to-index example requires sourced exposures and dated weights; synthetic test chains must remain clearly labelled.

## Reusable agent briefs for the next milestone

### Track 1: collection and provenance

Implement with Luna at low effort; request Sol at low effort for unresolved planning. Own the collectors, ingestion CLI, source registry and their tests. Extend the permitted source set toward issuer disclosures, Indian policy and relevant global policy using existing HTTP/feed adapters. Persist actual source responses, immutable revisions, first observation, publication uncertainty, issuer IDs and source rights. Repeated observations must not move the historical first-seen time. Partial runs must preserve successful evidence and expose failure status. Accept only after a real refreshed batch, duplicate/revision checks and coverage report pass. Document precisely which company/date coverage remains missing; do not invent dates or exposure mappings. Only add Firecrawl/Crawl4AI for a specific source requirement.

### Track 2: evidence assessment and relationships

Implement with Luna at low effort; use Sol at low effort for design changes. Own the relationship store, structured assessment integration and their tests. Extend the existing budgeted Nova annotation boundary to produce source-supported claims, explicit authority/corroboration fields and proposed directed exposure links. Validate citations against the supplied text, preserve unknowns, and retain the assessment's completion time. Start with a reviewed real policy-to-exposure example and dated sector/index identities. Retrieve eligible historical cases by entity, event type, regime and horizon; unmatched cases must not be presented as support. Accept only after a real report traces every link to evidence and passes future-leakage, correction, double-counting and time-horizon checks. Keep impact predictions unvalidated until measured.

### Track 3: independent verification and operation

Use Luna at low effort for verification and Sol at low effort for planning. Own integration checks and the operations status document; coordinate shared log updates through root. Reconcile the stale merged candle artifact without changing frozen evaluation inputs, then verify a fresh market-data handoff and budgeted provider readiness. Independently test collection → database → annotation → shadow snapshot → paper journal, including provider failure, partial feeds, restart, chronology and budget exhaustion. Collect prospective results before scheduling candidate learning. Accept only with saved real run evidence and named unresolved gaps. A fixture pass, a provider smoke, and an unattended working session are different evidence levels.

All tracks preserve current risk limits, local Breeze credential isolation and the existing holdout. Root coordinates integration and the project log. No track may silently promote scores or policies into live trading.
