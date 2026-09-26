# Momentum investing and trading blueprint

## Recommended direction

Build a personal, evidence-driven investing and trading system with two separate research mandates and one shared risk controller. Begin with Indian cash equities, daily observations, low turnover and simulated execution. The investing mandate studies business value over years; the trading mandate tests price behaviour over days and months. Both may conclude that cash is the best available action.

The starting financial constraint is INR 10,000 plus at least INR 2,000 monthly. At that scale, avoiding uneconomic transactions and recurring technology bills matters as much as finding promising securities. Low share price is an affordability characteristic, not evidence of cheap valuation or rapid future growth. Market capitalization, dilution, cash generation, financing needs and the price paid for those economics determine the investment case.

The recommended first stack is the existing Momentum dashboard, the existing Python research package, a local research worker, versioned files, a small durable job ledger and Groq for bounded document tasks. Start the broker evaluation with Upstox's read-only analytics access; compare Zerodha and Dhan for eventual low-turnover delivery execution. This is a conditional implementation recommendation, not a finding that a strategy already earns excess returns.

All broker terms, API capabilities and regulatory references below were checked against primary sources available on 11 September 2026. Proposed thresholds, budgets and performance targets are explicitly design choices. No new strategy backtest, model comparison, credential validation or live-execution benchmark was performed for this report.

## Current platform and readiness

The repository contains meaningful research and simulation components, but it does not yet establish an investable edge. Code existence, passing software tests, valid citations and profitable trading are separate forms of evidence.

| Area | Observed implementation | Remaining requirement |
|---|---|---|
| Research foundation | Python collectors, financial normalization, governance rules, source records and recommendation validation | Complete current evidence, publication-time histories and broader issuer coverage |
| Momentum interface | Finance research, investing, daily-history and paper-trading components | Verify the integrated build and hosted behaviour after the latest changes |
| Universe | A broader company identity list exists; seeded financial evidence remains concentrated in ten companies | Distinguish searchable identity, complete evidence and strategy eligibility |
| Groq | Server-side integration selects openai/gpt-oss-20b and requests JSON output | Confirm a valid configured credential with a controlled smoke test; add strict schemas and usage accounting |
| Investing agents | Fundamentals, governance and valuation roles followed by synthesis over a frozen evidence snapshot | Full-document extraction, claim-to-passage verification, durable jobs and prospective evaluation |
| Trading | Single-security breakout simulation with chronological development/test segments | Portfolio simulation, contributions, current and historical fees, point-in-time membership and robust holdouts |
| Paper trading | Whole-share sizing, event records and simulated fills | Exact strategy parity, account-wide risk, reconciliation and operational fault testing |
| Brokerage | No verified order gateway in the inspected finance path | Broker selection, compliant authentication, execution controls and explicit live activation |

These observations come from the inspected source files, rather than an assumption that historical project-log checkpoints describe today's deployment.[^50]

Two issues take priority over adding more models. First, the backtest sets its stop at entry price minus two ATR units, where entry is based on the next opening price. The paper path accepts a stop calculated from the signal closing price. A gap therefore changes risk, sizing, eligibility and target behaviour differently. Choose one complete specification, apply it in both paths and invalidate comparisons across the old definitions.

Second, the market adapter scales historical OHLC by adjusted close while retaining vendor volume. Adjusted prices are useful for return calculations, but they cannot directly represent historical rupee affordability and share counts. Maintain actual execution prices and corporate actions separately. Model splits, bonuses, dividends and changing quantities without double-counting their returns. The current simple backtest also excludes monthly contributions, so it cannot answer the personal capital-plan question.

## Investor methods translated into agent work

Public accounts of successful investors reveal useful decision disciplines. They do not reveal a complete, reproducible source of future excess return. Famous winners also have unusual experience, access, capital structures and favourable surviving examples.

| Method | Transferable principle | Agent output | Boundary |
|---|---|---|---|
| Buffett | Understand business economics, returns on capital, reinvestment and price | Per-share earnings bridge, capital-efficiency history, valuation scenarios and thesis failure conditions | A quality screen cannot reproduce Berkshire's judgment or financing |
| Lynch | Familiar products can generate leads; investigate economics and expansion | Discovery note followed by competition, balance-sheet and runway evidence | Product familiarity cannot approve an investment |
| Marks | Understand permanent-loss paths and expectations; remain humble about macro forecasts | Financing stresses, reverse valuation, downside scenarios and contrary evidence | A confident macro narrative cannot become a buy trigger |
| Quality/profitability research | Test whether profitable, financially resilient businesses offer useful signals | Sector-appropriate, point-in-time factors with explicit definitions | Historical factor results require local validation after costs |

Berkshire's owner's manual and 2007 letter support business ownership, capital efficiency and sensible purchase prices.[^1][^2] Lynch's own Fidelity discussion treats familiarity as the start of further investigation.[^3] Marks distinguishes useful risk assessment from the illusion of reliable macro forecasting and emphasizes long-term value and asymmetry.[^4][^5]

Novy-Marx and Quality Minus Junk provide empirical reasons to investigate profitability and quality. Their populations and constructions differ from a small Indian delivery portfolio; Quality Minus Junk includes long-short portfolios. Research on the historical cross-section also demonstrates how apparent accounting anomalies can weaken outside their discovery samples. These are starting hypotheses, not a ready-made Indian stock list.[^6][^7][^8]

The investing workflow should make each role accountable for a narrow deliverable:

1. **Evidence collector:** collect official filings, announcements, ownership disclosures and corporate actions; resolve issuer identity; record gaps.
2. **Accounting analyst:** extract units, period, reporting scope and values, then reconcile them with deterministic arithmetic.
3. **Business analyst:** describe revenue drivers, customer concentration, competitive advantage and reinvestment runway. Separate observations from interpretations.
4. **Governance reviewer:** flag auditor qualifications, unexplained related-party balances, promoter pledges, dilution and contradictions using filing passages.
5. **Valuation analyst:** calculate bear/base/bull scenarios and reverse valuation. Show which assumptions drive the range.
6. **Skeptic:** identify the strongest alternative explanation and conditions that would invalidate the thesis.
7. **Risk controller:** check data completeness, liquidity, affordability and portfolio exposure.
8. **Decision recorder:** preserve every eligible, rejected and unresolved case, along with its evidence and future review date.

These are logical responsibilities, not eight permanent paid AI processes. Collection, arithmetic, eligibility and recording should primarily be code. Several analyses can share one evidence packet, while expensive qualitative review is reserved for a short list.

Banks and other financial companies need separate templates. Industrial-company free cash flow, working capital and net debt ratios do not map cleanly to banks. Bank research needs asset quality, provisioning, capital adequacy, deposit economics and credit costs; RBI capital and prudential rules provide the relevant primary framework.[^23][^24]

The main governance feed should remain exchange/company disclosures under the current LODR framework. Surveillance, pledges, insolvency and trading restrictions require current checks. A surveillance label warrants review; it is not, by itself, a finding of wrongdoing.[^21][^22]

## Trading methods and the initial experiment set

Systematic trading begins with a precise hypothesis, an executable rule and a test designed to disprove it. Persistence and momentum are reasonable initial subjects because their published evidence spans long histories. The trend literature often studies diversified futures with long and short positions, while classic cross-sectional momentum ranks relative winners and losers. Neither directly proves profitability for a few long-only NSE stocks.[^9][^10]

The first implementation should preserve the existing breakout as a baseline after fixing parity. Adding a different 100-day rule during validation would introduce another experiment, not repair the existing one. Register at most three initial families; count every parameter choice and rejected variation.

Live institutional execution research finds that trading costs vary with characteristics of the trade, stock and time. Its institutional cost estimates should not be transplanted into this account, but the evidence supports explicitly modelling execution conditions rather than assuming frictionless fills.[^14]

| Experiment | Frozen initial research definition | Review frequency | Purpose |
|---|---|---|---|
| Existing breakout baseline | Prior 20-session high, 200-session average, volume filter, 14-session ATR, one agreed stop/target convention and 20-session time exit | Daily after completed data | Test the strategy already represented in the product |
| Relative momentum | Rank eligible stocks by return from 12 months ago to one month ago; apply a 200-session trend filter; rebalance monthly | Monthly | Test a lower-turnover alternative |
| Quality-growth investing | Sector-appropriate profitability, cash conversion, dilution and financing screens; valuation and evidence gates | Quarterly and on material filings | Test a business-based selection process |

Use a historical liquidity-qualified universe broad enough to include failures, with listing-age and data-completeness requirements fixed beforehand. Low nominal price should not be a ranking signal. Initially exclude instruments whose board, lot size, restrictions or liquidity cannot be simulated reliably. Portfolio construction must respect the capital and cost limits even if that means no position.

Short-term reversal, more breakout lengths, intraday signals and ML are challengers for later cycles. There is no reason to spend the account's limited research budget searching a large strategy zoo before the first three families pass basic integrity checks.

Prediction accuracy is not the economic objective. In illustrative risk units, winning 40% of trades at 2R and losing 60% at 1R gives 0.2R average profit before costs. Winning 80% at 0.2R but losing 20% at 2R gives a loss of 0.24R. Actual gaps, fills and charges can change either result.

Retail outcome evidence supports a cautious starting scope. SEBI's cash-equity intraday study found seven out of ten individuals lost money. Its August 2026 derivatives release reports an 87.7% loss rate for FY26 individuals in the studied population. These findings concern intraday cash trading and derivatives, not the proposed swing strategy.[^15][^16] The same derivatives release classifies an entity as algorithmic if it placed at least one algorithmic trade in the year; its aggregate algo-profit figures do not establish that AI agents or retail automation cause profitability.[^16]

## Capital, transaction costs and broker comparison

A research tool needs its own spending ledger. An INR 500 monthly data subscription costs INR 6,000 annually: 60% of the initial INR 10,000, and 25% of the planned INR 2,000 monthly contribution. Those denominators describe expense burden; they are not a calculation of the portfolio's required annual return, because cash arrives over time.

| Provider | Research access currently documented | Resident retail equity-delivery brokerage | Fit for this project |
|---|---|---|---|
| Upstox | Free analytics token valid for one year; supported historical, quote, fundamental and news access | INR 20 per executed order | First research-access candidate; fixed delivery brokerage disadvantages small frequent tickets |
| Zerodha | Personal API free without historical/real-time market data; Connect data access INR 500/app/month | Zero for ordinary resident retail individual delivery accounts | Execution shortlist; initially avoid paying for a second data feed |
| Dhan | Data API INR 499 plus tax monthly | Zero delivery brokerage | Execution shortlist; paid data is unnecessary if another permitted source meets requirements |

The table combines the providers' current API documentation and charges pages.[^25][^33][^34][^35][^36][^37] Zero brokerage does not remove depository charges, taxes, exchange charges, spread or slippage. Account type, account maintenance, BSDA eligibility and special trading arrangements can alter the total bill.

For an illustrative INR 2,000 delivery purchase and later sale, two INR 20 Upstox orders cost INR 40 in brokerage. Adding 18% GST on that brokerage gives INR 47.20, or 2.36% of the position, before all other charges. That almost consumes an illustrative INR 50 planned trade-risk budget. Use the broker tariff effective on the transaction date and reconcile against contract notes; a constant basis-point fee cannot represent fixed and per-ISIN charges accurately.[^33]

A broker decision should follow a small acceptance exercise: verify account eligibility, credential renewal, required data coverage, corporate-action handling, tariff calculation and sandbox or manual reconciliation. The provisional choice is Upstox for research evaluation, with Zerodha and Dhan compared for delivery execution. Prefer an existing suitable account where possible; opening multiple accounts solely to combine features may introduce costs, administration and eligibility changes.

Research-provider choice and execution-broker choice can be separate, but access does not automatically grant cross-provider or public redistribution rights. Retain private research use until the relevant agreements are checked. NSE's data policy makes permitted use and redistribution a contractual question.[^20]

### Feasibility before position sizing

Do not force a fixed number of holdings. First estimate the minimum economically viable ticket from fixed round-trip costs and a declared friction budget, then add variable costs and liquidity impact. In the Upstox example above, INR 40 round-trip brokerage plus INR 7.20 GST needs a ticket of at least INR 4,720 merely to keep those charges at 1%, before other charges and market impact. That exceeds a 20% position limit on INR 10,000, so the correct outcome under those constraints is to skip the trade or revisit the broker choice, rather than force deployment.

For trading, choose the largest whole-share quantity satisfying all of these inequalities:

- Purchase value plus entry charges is within available settled cash.
- Position value is within the portfolio concentration limit.
- Planned loss to the stop, estimated exit charges and slippage are within the risk budget.
- Order value and stressed exit size are feasible in the actual market.
- Expected opportunity remains worthwhile after conservative total costs.

Because fees are nonlinear, solve the quantity constraint using the tariff function and check the resulting integer, rather than using one percentage-fee formula. A proposed paper default is at most 0.5% of account equity in planned stop risk per new trade and 20% in one position, matching the current app's broad starting settings. These are experimental constraints, not an accepted personal loss tolerance. Stops cannot cap losses during gaps or an inability to sell.

Long-term investing needs a thesis-downside and concentration budget rather than an arbitrary trading stop. An INR 10,000 account may not support both several viable direct-stock positions and meaningful diversification. Accumulating monthly contributions, retaining cash and using a diversified fund as a separately evaluated alternative are valid outcomes. Never loosen a rule merely to make the dashboard show a purchase.

Liquidity evaluation should combine actual spread/depth, low-volume days, trading restrictions and stressed exit assumptions. NSE explains that impact cost depends on order size, side and the available order book.[^19] A volume percentage alone is insufficient. Start with conservative order participation limits, then calibrate them against observed depth; lack of reliable execution evidence should block an order.

## Data sources and API contracts

The data layer must answer two questions: what is known now, and what was knowable at a historical decision time? A provider's historical reporting-period labels answer neither publication timing nor the vintage of a restated value by themselves.

| Need | Preferred source and interface | Acceptance test |
|---|---|---|
| Instrument identity | Exchange security masters plus broker instrument mapping | ISIN, symbol history, listing/exit dates, board, lot and tick size agree |
| Daily prices | Upstox V3 historical candles; independently sampled official exchange records | Calendar, timezone, sorting, missing bars, price scale and actions reconcile |
| Financial statements | Official company/exchange filings as authority; Upstox fundamentals as convenience layer | Consolidated/standalone scope, currency, crore/lakh units and publication dates agree |
| Ownership | Official shareholding/pledge disclosures plus provider history | Quarter labels do not substitute for publication timestamps |
| Corporate actions | Exchange/company notices and provider action records | Ex-date, record/payment date, ratio and actual holdings effects reconcile |
| News | Official announcements first; Upstox linked news for discovery | Original link, publication time, retrieval time, duplicate and correction handling |
| Benchmarks | Licensed/authorized total-return index histories | Total return rather than price index; calendar and cash-flow dates match |
| Execution | Selected broker's order, trade, funds and position APIs | State reconciles with broker records and contract notes |

The first adapter contracts should use the following documented endpoints, with credentials held on the server:

- Historical candles: GET https://api.upstox.com/v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}.[^26]
- Balance sheet: GET https://api.upstox.com/v2/fundamentals/{isin}/balance-sheet?type=consolidated&fs=true.[^27]
- Ownership: GET https://api.upstox.com/v2/fundamentals/{isin}/share-holdings.[^28]
- Corporate actions: implement against the provider's documented corporate-actions schema and verify event semantics before portfolio use.[^29]
- News: GET https://api.upstox.com/v2/news?category=instrument_keys&instrument_keys=...; up to 30 instruments per request, with pagination.[^30]

Upstox documents daily history availability from January 2000 with at most a decade per request, and minute/hour history from January 2022 with smaller request windows. These are endpoint availability limits, not proof that every listed or delisted stock has complete history.[^26] Start with a coverage audit before promising a multi-decade backtest.

The balance-sheet endpoint explicitly distinguishes reporting scope and uses crore-denominated monetary fields; its detailed statement is annual. The documented ownership example returns quarterly history. Neither establishes a complete historical archive of values as originally published. Store each retrieval as a new vintage and use original filings for historical eligibility.[^27][^28]

The news endpoint covers only the past seven days. It returns article links and publication timestamps in milliseconds. Therefore it is a useful current digest source, not a historical news dataset for backtesting. Archive permitted metadata and extracted facts prospectively, detect missed collection intervals, and link readers to original articles.[^30]

The analytics token is read-only. Supported public-market GET categories do not need static IP, while private-account GET categories can require it. Do not confuse this with permission to submit orders.[^25] The adapter should declare capabilities explicitly and reject unsupported operations before making a network request.

Apply one shared rate limiter per provider/account, including all agents and retries. Upstox's standard API limits include 50 requests/second, 500/minute and 2,000/30 minutes. A conservative backfill budget should stay well below every window, prioritize new daily data and honour backoff.[^31] Save checkpoints so a failed batch resumes without repeating the entire universe.

NSE offers official historical/EOD products, but paid or licensed data acquisition should follow a demonstrated gap in the inexpensive sources. Public-page availability and a successful request do not establish a stable supported integration or permission to republish data.[^20][^51]

## Evidence storage and retrieval

Use immutable raw inputs and versioned derived outputs. The essential records are:

| Record | Required fields |
|---|---|
| Instrument | Internal ID, ISIN, exchange symbol, validity interval, board, lot/tick, listing and delisting status |
| Source artifact | Source URL, publisher, publication time, first-seen time, retrieval time, hash, document version, permitted use |
| Financial fact | Issuer, metric, value, unit, currency, period, consolidated/standalone scope, source page/table, original/restated vintage |
| Market bar | Instrument, session, raw OHLCV, completion time, provider, retrieval version and quality flags |
| Corporate action | Instrument, type, announced/ex/record/payment dates, ratio or amount, source and processing state |
| Feature snapshot | Instrument, decision time, feature version, source hashes, training cutoff and missing-value flags |
| Research decision | Evidence snapshot, claims, calculations, scenarios, contrary evidence, status, model/prompt versions and review triggers |
| Experiment | Hypothesis, parameters, universe version, splits, fees, code/environment hashes, attempted variants and results |
| Order intent | Account, strategy version, decision ID, side, quantity, price constraints, expiry and approval scope |
| Execution ledger | Intent ID, broker order ID, state transitions, fills, fees, cash changes and reconciliation status |

Store times in UTC with the Indian exchange session date recorded separately. A financial period ending March 31 must not become usable on March 31 unless the information was actually public then. Later corrections append a vintage rather than overwriting the historical evidence. Current scores should use the most appropriate valid vintage; simulations should use only vintages available at their decision time.

Freshness rules should depend on the information. Prices need a completed session, news needs publication and collection timestamps, and annual versus quarterly statements need different due-date logic. A universal filing-age threshold cannot tell whether a recently due quarterly result is missing.

Start document retrieval with issuer, period, document type and section filters plus full-text search. This is easier to audit than embedding the entire universe first. Introduce a vector index only if measured retrieval misses justify it. Keep exact page/table anchors so a reader can verify each numerical and qualitative claim.

Documents and news are untrusted inputs. They must never supply instructions, tool permissions or new secret destinations to the agent. Keep source extraction separate from execution; validate outbound source domains, file sizes and document types, and prevent retrieved content from altering workflow policy.

## Models, machine learning and efficiency

There are two distinct model decisions: models used by development assistants, and models called by the running platform. Luna, Terra medium and Sol medium can divide implementation and review work where available in the development environment. They should not be assumed to be public runtime API identifiers.

For the platform, use the least expensive method that passes the relevant evaluation:

| Task | Initial method | Escalation | Success measure |
|---|---|---|---|
| Prices, indicators, accounting arithmetic, costs and sizing | Deterministic code | Investigate source or formula conflicts | Exact reconciliation and reproducibility |
| Document classification and field extraction | Groq gpt-oss-20b with a strict schema | gpt-oss-120b or human review for difficult evidence | Correct value, unit, period, scope and passage |
| News digest | Deduplicate first; small model summarizes relevant new events | Larger model only for material contradictions | Grounded claims, useful coverage and cost |
| Investment synthesis | Small model over verified evidence | Larger model for a difficult thesis or contradiction | Traceability, contrary evidence and calibrated abstention |
| Return/risk prediction | No-ML baseline, then regularized linear model | LightGBM if it improves held-out economic results | Net return quality, drawdown, stability and calibration |
| Order submission and reconciliation | Deterministic state machine | Human attention on unresolved state | No unapproved or duplicate economic action |

Gu, Kelly and Xiu demonstrate that nonlinear methods can improve return prediction in a large US asset-pricing panel. That does not supply an Indian model, validated features or a small-account return estimate.[^11] LightGBM offers efficient tree learning and ranking objectives, making it a reasonable CPU-based challenger after simpler models.[^45] Begin with lagged momentum, volatility, volume/turnover, market trend and verified accounting features; do not add hundreds of correlated indicators merely because they are available.

A first ML label can be the next 20-session return relative to a declared benchmark, measured from the next executable entry and accompanied by a cost estimate. Construct labels only after all their future observations exist. Train transformations, missing-value handling, feature selection, calibration and hyperparameters inside training/validation windows. Ranking skill is not sufficient if the portfolio cannot afford the selected shares.

Use a fixed, small search budget, such as a maximum of 20 fully recorded configurations in the initial ML cycle. Compare an elastic-net baseline with shallow, regularized boosted trees and early stopping. Retrain on a scheduled research cycle, not on every new headline. Freeze the selected model during a forward evaluation period.

### Groq routing and cost

The current Groq page lists gpt-oss-20b at USD 0.075 per million input tokens and USD 0.30 per million output tokens; gpt-oss-120b is USD 0.15 and USD 0.60 respectively.[^39] For an illustrative call using 8,000 input and 1,000 billed output tokens, those rates give USD 0.0009 and USD 0.0018. Three small-model calls plus one large-model call would therefore cost USD 0.0045, or USD 0.45 for 100 such reports. Actual token use, reasoning output, retries, taxes and other services can change that estimate.

Provider tokens-per-second figures do not measure document download, retrieval, queueing, reasoning, validation or end-to-end quality. Record measured p50/p95 latency and invoice-compatible usage per task. A larger model should be promoted only if its improvement on the local evaluation set justifies the extra latency and cost.

Groq supports strict JSON-schema output for both selected models. The documented strict mode requires all properties to be required and disallows additional properties; structured output currently does not combine with streaming or tool use.[^40] Fetch evidence first, then make a bounded extraction call. Continue local schema and semantic validation: valid JSON can still contain an incorrect fact.

Cache by source hash, issuer/period/scope, task, schema version, prompt version and model version. Do not cache a live risk decision across changed prices or positions. Use one synthesis after parallel independent analyses, rather than repeated agents rewriting the same conclusion. Route material conflicts to a larger model once, then return unresolved evidence if the conflict persists.

Groq's batch service offers a 50% discount with completion windows from 24 hours to seven days. It fits historical extraction and offline evaluations, not time-sensitive trading or a fresh daily digest.[^41] A proposed initial incremental R&D target is INR 0–200 monthly, separately tracked from invested capital. It is a budget policy, not a service quote or promise that all hosting/data costs fit within it.

### Hardware and scheduling

The inspected computer has an Intel Core i7-8650U, four physical cores/eight logical processors, approximately 15.8 GiB RAM and Intel UHD 620 graphics. No discrete GPU was observed. Use it for daily-data research, extraction preparation and modest linear/tree experiments; use hosted inference for language tasks. A GPU purchase is not justified by any measured bottleneck yet.

An illustrative 500-stock, ten-year daily dataset contains about 500 × 252 × 10 = 1.26 million bars before listing gaps. One year of one-minute bars at 375 minutes/session would contain about 47.25 million rows. Neither count represents independent training examples. Daily-first research reduces collection, storage, operational and validation demands.

Start with at most two concurrent CPU jobs and a total thread budget that leaves the machine usable; profile memory before increasing it. Limit concurrent LLM calls and enforce the account's real token/request quotas. Keep long downloads and training outside interactive website requests.

| Benchmark target, not a measured result | Initial budget | Measurement |
|---|---|---|
| Cached dashboard read | p95 under 1 second | Server and browser timings |
| Daily feature calculation for 500 symbols already on disk | Under 60 seconds | Wall time, peak memory, missing-feature count |
| Standard company evidence synthesis | p95 under 120 seconds | Retrieval plus all calls and validation |
| Small-model extraction call | p95 under 30 seconds | End-to-end request timing, including failures |
| Initial bounded ML experiment cycle | Under 30 minutes on local CPU | Full cross-validation/training cost and memory |
| Daily paper reconciliation | Complete before the next actionable session | Data freshness, unresolved-state count and job completion |

If a target fails, profile the bottleneck before changing models or infrastructure. None of these targets is a production service-level guarantee.

## Benchmarks and promotion gates

There are three evaluation layers. A better language model does not imply a better trading strategy, and a profitable historical strategy does not imply a reliable execution system.

### Document and reasoning quality

Create a local gold set of approximately 200 Indian filing questions plus 50 adversarial, contradictory or insufficient-evidence cases. Include crore/lakh conversions, per-share metrics, consolidated versus standalone reports, negative numbers, restatements, bank-specific measures and missing periods. Separate development and held-out cases by issuer and reporting period where practical.

FinQA provides a useful format for financial numerical reasoning with supporting evidence and calculations; FinanceBench provides a useful financial question-answering evaluation pattern. Their published datasets and historical model results do not establish performance on the project's current models or Indian filings.[^48][^49]

Proposed release criteria are zero critical unit, currency or period errors on the held-out critical subset; zero invented source IDs; at least 95% supported-claim precision on adjudicated claims; and a separately measured abstention rate on unanswerable questions. Report sample counts and uncertainty, not only percentages. Failing critical evidence cases should block that task category or route it to review.

Measure extraction accuracy, retrieval recall, citation entailment and numeric correctness separately. A citation is only a pointer; entailment asks whether the cited passage actually supports the claim. Agent agreement is not independent evidence when agents share the same model and inputs.

### Strategy validation

Use one portfolio simulator with matching contribution dates for strategies and benchmarks. Report time-weighted returns for strategy comparison and money-weighted return/XIRR for the personal capital experience. Deposits must not be counted as profit. Include idle cash, distributions, whole shares, all explicit charges and realistic fills.

Compare against cash, a broad Indian total-return benchmark and a universe-appropriate small-cap benchmark when testing small caps. Distinguish the theoretical index from an investable fund/ETF implementation with expenses, tracking differences and trading costs. Include a cash-exposure-matched comparison as a diagnostic, rather than silently changing the primary benchmark after results arrive.

A practical first design is expanding chronological training, a subsequent validation block and an untouched test block, repeated forward. For a sufficiently long dataset, start with five years training, one year validation and one year test; shorten only with an explicit loss-of-confidence note. Seek several market regimes and multiple years of aggregate out-of-sample evidence. Keep a final block unseen until the specification is frozen. Reopening it turns it into development data.

Split the entire stock panel by date, not random rows. Purge training labels whose future outcome interval overlaps validation/test intervals. Add an embargo where residual leakage/dependence warrants it; an arbitrary gap is not a substitute for understanding the label interval. The ordinary TimeSeriesSplit tool supports chronology and a gap, but it does not automatically implement panel-aware purging or point-in-time fundamentals.[^46]

Track rank correlation, top-ranked selection outcomes, calibration and economic results. Brier score and log loss evaluate probabilistic predictions but mix more than calibration alone; also inspect reliability diagrams and performance by market regime.[^47] Do not display an LLM's self-reported confidence as a probability of profit.

For economic promotion, require positive net excess results across aggregate out-of-sample periods, tolerable drawdowns under a predeclared mandate and no dependence on a single stock, year or favourable cost assumption. Stress twice estimated spread/slippage, missing fills, delayed entry, lower trading volume and removal of the best period. Examine sensitivity around parameter choices rather than celebrating a narrow optimum.

The Deflated Sharpe Ratio and Probability of Backtest Overfitting help assess selection effects, non-normality and the instability of selected winners.[^12][^13] Report their assumptions and the full trial count. Thresholds such as 95% DSR probability or PBO below 20% can be preregistered diagnostics, but they are not universal approval certificates, especially with few correlated observations. Bootstrap date blocks and assess sector/time dependence instead of treating every stock-day or trade as independent.

A hundred completed positions is a useful sample-size warning threshold, not proof of an edge. A short strategy history, a survivor-only universe or unknown filing vintages can make an attractive statistic unusable. When valid historical data are unavailable, label the result exploratory and begin a prospective record rather than fabricating precision.

### Historical AI leakage

A modern language model may already know later scandals, delistings, business outcomes and stock winners. Supplying an old report does not remove that knowledge from its parameters. Even issuer anonymization and an advertised training cutoff do not prove that a historical qualitative recommendation was genuinely out of sample.

Backtest deterministic features, accounting formulas, mechanical valuation rules and portfolio policies using point-in-time evidence. Test LLM extraction against historical documents for clerical accuracy. Validate qualitative moat assessments, governance judgments and discretionary AI selection prospectively through frozen models/prompts, timestamped inputs, outputs, rejections and shadow portfolios. Do not attribute historical returns to present-day narrative intelligence.

### Execution and forward evaluation

Use sandbox testing for protocol correctness. Upstox's sandbox has separate tokens and supported APIs; it does not establish real-market fill quality or strategy profitability.[^32] Then run the frozen strategy in paper mode through actual collection times, missed data, holidays and model/provider failures.

A first 8–12-week paper period can expose operational defects. A six-to-twelve-month record gives a broader operational sample, but cannot validate a multiyear investment thesis or establish excess return by itself. Promotion depends on evidence sufficiency, not a calendar promise.

Required failure tests include repeated job delivery, timeouts after order submission, duplicate/out-of-order callbacks, partial fills, rejected orders, expired credentials, market gaps, stale prices, incorrect corporate actions, clock/timezone errors and unavailable funds. Each unresolved order or reconciliation discrepancy must block new exposure until understood. Keep simulated, sandbox and live P&L visibly separate.

## Architecture and agent communication

Reuse the current platform rather than introducing a second dashboard. Treat the Site as the private control and reporting surface, the Python worker as the research engine, and a future broker adapter as a separately permissioned execution component.

| Layer | Initial implementation | Responsibility |
|---|---|---|
| Momentum Site | Existing React/Vinext application and authenticated server routes | Budget, watchlist, evidence reports, jobs, experiment results and paper ledger |
| Control database | Existing D1 for account-scoped job metadata and dashboard projections | Durable status, settings, run references and access control |
| Research worker | Existing Python package extended with a bounded job runner | Collect, normalize, calculate, evaluate and publish results |
| Research storage | Versioned Parquet/files plus DuckDB for analysis; local SQLite job/run metadata where needed | Reproducible inputs, research queries and resumable local work |
| AI adapter | Existing Groq integration with typed output, validation, cache and budgets | Bounded evidence tasks |
| Paper engine | One authoritative strategy/state definition shared with historical replay | Simulated orders, holdings, fees and diagnostics |
| Future live gateway | Broker-approved authentication and required network controls | Revalidate approved intent, submit once, reconcile and monitor |

Choose one authoritative store for each record. D1 owns Site job/control state; immutable research snapshots own input evidence; the execution ledger owns intent/fill state. Do not write the same mutable portfolio independently into D1, SQLite and another cloud database. Any existing alternative store should be evaluated for reuse or migration before adding another service.

For local research, the worker can make authenticated outbound HTTPS requests to claim jobs and publish results. This avoids exposing a listening port on the personal computer. Use expiring leases, heartbeat timestamps, content hashes and authenticated callback requests. Worker credentials must be scoped to the relevant jobs/account; sign requests with expiry and nonce/replay protection if using a custom callback protocol.

The machine sleeping or disconnecting should leave a visible stale/offline status, not an apparently healthy automation. An unattended live executor would need independent uptime and, where required, a stable whitelisted egress IP. Do not assume the hosted Site supplies that network property. Obtain an actual deployment quote only after a live gateway is justified.

A job envelope should include run_id, parent_run_id, account_id, job_type, schema_version, idempotency_key, as_of, input_snapshot_hash, strategy_version, budget, attempt, lease_until and trace_id. Outputs should include status, evidence_refs, metrics, unresolved_items, timestamps and artifact_hash. The status vocabulary should distinguish queued, running, needs_data, needs_review, succeeded, failed and cancelled.

Agent communication should pass these records through the orchestrator. An investing analyst can request missing evidence; a trading researcher can request an approved backtest specification. Neither can change the global risk policy, increase its own budget or invoke an order tool. Disagreement should create a review item with conflicting passages or calculations, rather than a vote that hides the uncertainty.

The orchestrator deduplicates collection, shares frozen inputs, runs independent analyses concurrently, validates outputs and records one decision. Use dependency-aware scheduling: collect before extraction, reconcile facts before valuation, and freeze decisions before execution. Audit traces should contain operational events and concise rationales, not hidden reasoning transcripts.

### Framework decision

| Option | Appropriate use | Decision |
|---|---|---|
| Plain typed Python functions plus durable jobs | Small fixed workflow with clear inputs and outputs | Start here; lowest integration burden |
| LangChain | Standard model/tool integration and agent abstractions | Adopt a component only when it replaces code the project actually needs |
| LangGraph | Explicit state transitions, parallel branches, checkpoints and human review | Add when the growing workflow needs durable pause/resume and inspection |
| Multiple-agent debate framework | Open-ended agent conversations | No initial requirement; measure benefit before adding cost |
| Provider routing proxy | Multiple hosts, fallback policies and shared budgets | Defer while one Groq adapter is sufficient |

LangChain's current agent abstraction builds on LangGraph; it need not be a mandatory dependency for every model call. LangGraph distinguishes fixed workflows from dynamic agents and supports persistence through checkpointers.[^42][^43][^52] For this product, a bounded graph is easier to review than a general agent deciding which financial tools to call next.

If LangGraph is introduced, select a persistent store appropriate to deployment and back it up. An in-memory saver is not durable across process loss. Interrupt/resume can restart a node from its beginning; therefore never place an external order before a review interrupt and assume it will not execute again.[^43][^44]

Use an outbox and an explicit order state machine: draft, approved, submitting, acknowledged, partially_filled, filled, cancelled, rejected or unknown. Persist intent before calling the broker. After an ambiguous submission timeout, query/reconcile broker state before retrying. A local idempotency key alone cannot guarantee exactly-once broker execution.

Approval must be bound to account, strategy/version, side, maximum quantity, price bounds and expiry. Any changed proposal needs a new valid approval scope. Before submission, recheck funds, exposure, market state, order type and freshness. A kill switch blocks new submissions and requests cancellation where possible; it cannot guarantee liquidation during a halt or lower circuit.

## India execution requirements

SEBI's February 2025 retail-algo framework establishes broker-controlled API access, tagging and authentication/network requirements, with registration conditions tied to the specified order-rate threshold. The September 2025 extension makes the framework and exchange modalities applicable to all brokers from April 1, 2026.[^17][^18] Being below a registration threshold does not make an API order exempt from all controls.

Before implementing live routing, verify the selected broker's current onboarding, permitted order types, tagging, static-IP workflow, authentication renewal and account-specific limits against the latest exchange/broker requirements. Keep research-only credentials separate from trade-enabled credentials. A read-only analytics token must never be upgraded implicitly.

Broker sessions are another operational constraint. Kite documents expiry of its ordinary access token at 6 AM the next day, as well as earlier invalidation conditions.[^38] Authentication expiry must produce a visible inactive state and prevent new exposure. The architecture should not imply permanently unattended access where the broker requires periodic login.

No strategy, account or order authority is enabled by this blueprint. The first live stage, if later authorized and justified, should have a small defined capital limit, manual review, daily reconciliation and a tested broker-app fallback. Trading capital allocation requires both validated results and a defined personal loss budget; selecting the best backtest alone is insufficient.

## Dashboard and news digestion

Keep investing and trading visible as separate mandates with shared cash and exposure. The dashboard should explain why a candidate is eligible, blocked or awaiting evidence in ordinary language.

| View | Information to show |
|---|---|
| Overview | Contributions, cash, holdings value, realized/unrealized P&L, costs, drawdown, data freshness and mode |
| Investing | Thesis, valuation range, financial trends, governance flags, source passages, contrary evidence and next review |
| Trading laboratory | Frozen strategy version, sample dates, benchmark, costs, trade count, uncertainty and out-of-sample results |
| Paper portfolio | Signals, intended orders, accepted/skipped trades, actual collection time, simulated fills and reconciliation |
| News digest | What happened, affected issuer, supporting source, publication time, implication, uncertainty and follow-up |
| Agent activity | Current job, last successful run, blocked inputs, model spending and result link |

The default news workflow is event-driven collection plus a scheduled digest after the relevant market data are complete. Fetch only watchlist/holding-relevant material first, deduplicate by URL and content, identify the issuer, classify the event and attach the primary announcement where available. Write a short summary with a link and a separately labeled interpretation. Do not turn positive sentiment into an order.

For a material event such as an auditor resignation or financing announcement, the digest should request a fresh thesis/risk review. A summary alone should not overwrite the verified financial record. Record corrections and show when a source window was missed. The seven-day Upstox news limit makes reliable collection cadence particularly important.[^30]

Integrate through authenticated server routes and account-scoped result records, not browser-held broker keys. Keep private holdings and licensed market content behind authentication. A future public Momentum page could show permitted original summaries and source links without exposing account data or redistributing a full third-party feed.

## Technical implementation sequence

The following is an ordered backlog. File names in this table are proposed additions unless explicitly described as existing. Delivery estimates concern engineering work only; obtaining valid historical data and accumulating forward evidence can take much longer.

| Priority | Work package | Concrete deliverable | Acceptance evidence |
|---|---|---|---|
| P0 | Establish one strategy definition | Versioned specification; align existing finance-core.ts, finance-paper.ts and signal construction; retain shared replay fixtures | Identical signals, stops, sizing, entries and exits for the same event sequence; documented end-of-test liquidation differences |
| P0 | Verify current integrated platform | Review latest changes, run appropriate checks and controlled local/hosted smoke tests | Recorded build/test outcome; explicit remaining failures; no inferred deployment success |
| P1 | Add read-only provider adapter | providers/upstox.py, capability/auth configuration, instrument mapping, rate limiter and resumable collection | Small sample reconciled against official records; missing/delisted coverage audit; no order permission |
| P1 | Version evidence | Evidence-vintage schema, corporate-action ledger and raw/derived price separation | Correct replay around publication, restatement, split, bonus and dividend dates |
| P2 | Build portfolio research engine | research/simulator.py, broker_tariffs.py, benchmark and contribution ledger | Cash/holdings invariants, whole-share feasibility, dated costs and matched benchmark cash flows |
| P2 | Freeze experiment registry | experiments/*.yaml, trial ledger, date-grouped splits and reproducibility manifest | No random panel split; overlap-purge tests; rejected variants retained |
| P3 | Harden model workflow | Strict schemas, passage verification, usage log, caching, timeouts and escalation limits in the existing provider flow | Indian filing gold-set results with error categories, costs and latency |
| P3 | Add durable research jobs and digest | jobs/worker.py, authenticated job routes and source-linked digest results | Restart/resume without duplicate records; stale/offline state; account isolation |
| P4 | Evaluate ML challengers | models/baselines.py, models/boosting.py and a reproducible evaluation command | Linear/boosting/no-ML comparison on identical data/splits/costs; no promotion on training scores |
| P5 | Operate prospective paper program | Frozen model/strategy versions and daily execution journal | Reconciliation, rejected/missed decision records, fault drills and qualified performance report |
| P6 | Build optional execution adapter | Approved broker gateway, intent/outbox ledger, reconciliation and emergency controls | Current broker requirements met; explicit activation; tiny constrained trial only after evidence gates |

P0–P1 can be planned as several focused engineering sessions; P2–P4 are likely multiple iterations driven by data defects and validation results. P5 takes calendar time that cannot be compressed by using more agents. No completion date or investment performance should be inferred from these estimates.

For implementation delegation, use Luna for bounded adapters, fixtures and straightforward UI wiring; Terra medium for simulator, data-model and worker integration; Sol medium for methodological review, broker-contract checks and evaluation interpretation. The orchestrator owns acceptance criteria, shared contracts and cross-component review. Use disjoint file ownership and a single integration path; do not have two agents independently rewrite the authoritative execution engine.

The first concrete deliverable should be the parity repair plus a read-only data coverage report. The next should be a contribution-aware, broker-cost-aware comparison of the frozen strategies. Only then can the dashboard responsibly answer whether direct investing, trading, a diversified benchmark or holding cash was the most effective use of the tested capital under the declared assumptions.

## Unresolved evidence and decision limits

The principal unknowns are the selected broker/account, the coverage and licensing of point-in-time Indian histories, valid runtime credentials, actual local model/latency measurements and the personal loss tolerance for live capital. None prevents building the research system; each affects later claims or execution.

No stock has been selected by this report. No projected CAGR, monthly income, win rate or ML accuracy is asserted. The platform has not yet demonstrated a repeatable edge after all costs. A useful system must be willing to reject an attractive story, an overfit strategy and an unaffordable transaction.

The recommended design creates a traceable path from evidence to experiments to decisions. Its near-term value is better research, fewer unsupported decisions and an honest performance record. Profitable deployment remains a hypothesis to test.

## Sources

Numbered references identify the exact primary pages or documents used. Undated live documentation and pricing pages were checked on 11 September 2026. Historical papers describe their original populations and methods; technical design choices and targets in this report are recommendations, not claims from those papers.

[^1]: Warren E. Buffett. [An Owner's Manual](https://www.berkshirehathaway.com/1996ar/manual.html). June 1996.

[^2]: Warren E. Buffett. [Berkshire Hathaway 2007 Shareholder Letter](https://www.berkshirehathaway.com/letters/2007ltr.pdf). 29 February 2008.

[^3]: Peter Lynch and Christopher Kuiper / Fidelity. [Understanding the Changing World of Investing, webcast transcript](https://www.fidelity.com/bin-public/060_www_fidelity_com/documents/learning-center/110322%20rewards%20exclusive_UnderstandtheChange-Transcript_%20F.pdf). 3 November 2022.

[^4]: Howard Marks / Oaktree. [The Illusion of Knowledge](https://www.oaktreecapital.com/insights/memo/the-illusion-of-knowledge). 8 September 2022.

[^5]: Howard Marks / Oaktree. [What Really Matters?](https://www.oaktreecapital.com/insights/memo/what-really-matters). 22 November 2022.

[^6]: Robert Novy-Marx / NBER. [The Other Side of Value: Good Growth and the Gross Profitability Premium, Working Paper 15940](https://www.nber.org/papers/w15940). April 2010.

[^7]: Clifford S. Asness, Andrea Frazzini and Lasse H. Pedersen. [Quality Minus Junk](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2312432). 5 June 2017 paper version.

[^8]: Juhani T. Linnainmaa and Michael R. Roberts / NBER. [The History of the Cross Section of Stock Returns, Working Paper 22894](https://www.nber.org/papers/w22894). December 2016.

[^9]: Brian K. Hurst, Yao Hua Ooi and Lasse H. Pedersen / AQR. [A Century of Evidence on Trend-Following Investing](https://www.aqr.com/insights/research/journal-article/a-century-of-evidence-on-trend-following-investing). 31 October 2017.

[^10]: Narasimhan Jegadeesh and Sheridan Titman. [Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency](https://doi.org/10.1111/j.1540-6261.1993.tb04702.x). March 1993.

[^11]: Shihao Gu, Bryan Kelly and Dacheng Xiu. [Empirical Asset Pricing via Machine Learning](https://academic.oup.com/rfs/article/33/5/2223/5758276). May 2020.

[^12]: David H. Bailey and Marcos Lopez de Prado. [The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality](https://doi.org/10.2139/ssrn.2460551). 31 July 2014.

[^13]: David H. Bailey, Jonathan M. Borwein, Marcos Lopez de Prado and Qiji Jim Zhu. [The Probability of Backtest Overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253). 27 February 2015 version; published 2017.

[^14]: Andrea Frazzini, Ronen Israel and Tobias J. Moskowitz / AQR. [Trading Costs](https://www.aqr.com/insights/research/working-paper/trading-costs). 23 August 2018.

[^15]: SEBI. [Study: Analysis of Intraday Trading by Individuals in Equity Cash Segment](https://www.sebi.gov.in/reports-and-statistics/research/jul-2024/study-analysis-of-intraday-trading-by-individuals-in-equity-cash-segment_84946.html). 24 July 2024.

[^16]: SEBI. [Studies Indicate Key Trends in Retail Participation, Trading Behaviour and Profitability in the Equity Derivatives, PR 50/2026](https://www.sebi.gov.in/sebi_data/attachdocs/aug-2026/1787236407005.pdf). 20 August 2026, pp. 1–3.

[^17]: SEBI. [Safer Participation of Retail Investors in Algorithmic Trading](https://www.sebi.gov.in/sebi_data/attachdocs/feb-2025/1738665456458.pdf). 4 February 2025.

[^18]: SEBI. [Extension of Timeline for Implementation of the Retail Algorithmic-Trading Circular](https://www.sebi.gov.in/sebi_data/attachdocs/sep-2025/1759232056254.pdf). 30 September 2025, paragraph 8.

[^19]: NSE. [Impact Cost](https://www.nseindia.com/static/products-services/indices-impact-cost). Updated 6 January 2023.

[^20]: NSE. [Data Usage and Sharing Policy](https://www.nseindia.com/static/market-data/nse-data-policy). Live policy page.

[^21]: SEBI. [Master Circular for Compliance with LODR Regulations by Listed Entities](https://www.sebi.gov.in/legal/master-circulars/jan-2026/master-circular-for-compliance-with-the-provisions-of-the-securities-and-exchange-board-of-india-listing-obligations-and-disclosure-requirements-regulations-2015-by-listed-entities_99432.html). 30 January 2026.

[^22]: SEBI. [Surveillance Measures](https://www.sebi.gov.in/curation/surviellance.html). Live reference page.

[^23]: RBI. [Master Circular: Basel III Capital Regulations](https://www.rbi.org.in/Scripts/BS_ViewMasterCirculars.aspx?Id=12815). 1 April 2025.

[^24]: RBI. [Prudential Norms on Income Recognition, Asset Classification and Provisioning Pertaining to Advances](https://rbi.org.in/scripts/NotificationUser.aspx?Id=12822). 1 April 2025.

[^25]: Upstox. [Analytics Token](https://upstox.com/developer/api-documentation/analytics-token/). Live developer documentation.

[^26]: Upstox. [Get Historical Candle Data V3](https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/). Live developer documentation.

[^27]: Upstox. [Balance Sheet API](https://upstox.com/developer/api-documentation/get-balance-sheet/). Live developer documentation.

[^28]: Upstox. [Share Holdings API](https://upstox.com/developer/api-documentation/get-share-holdings/). Live developer documentation.

[^29]: Upstox. [Corporate Actions API](https://upstox.com/developer/api-documentation/get-corporate-actions/). Live developer documentation.

[^30]: Upstox. [Get News](https://upstox.com/developer/api-documentation/get-news/). Live developer documentation.

[^31]: Upstox. [Rate Limiting](https://upstox.com/developer/api-documentation/rate-limiting/). Live developer documentation.

[^32]: Upstox. [Sandbox](https://upstox.com/developer/api-documentation/sandbox/). Live developer documentation.

[^33]: Upstox. [Brokerage Charges](https://upstox.com/brokerage-charges/). Current published tariff.

[^34]: Zerodha. [What Are the Charges for Kite APIs?](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/what-are-the-charges-for-kite-apis). Current support page.

[^35]: Zerodha. [Charges](https://zerodha.com/charges/). Current published tariff.

[^36]: Dhan. [How to Access Dhan API?](https://dhan.co/support/platforms/dhanhq-api/how-to-access-dhan-api/). Current support page.

[^37]: Dhan. [Pricing](https://dhan.co/pricing/). Current published tariff.

[^38]: Zerodha. [Kite Connect: User Authentication](https://kite.trade/docs/connect/v3/user/). Current v3 documentation.

[^39]: Groq. [Supported Models](https://console.groq.com/docs/models). Current production-model pricing and capability table.

[^40]: Groq. [Structured Outputs](https://console.groq.com/docs/structured-outputs). Current strict-mode documentation.

[^41]: Groq. [Batch Processing](https://console.groq.com/docs/batch). Current service documentation.

[^42]: LangChain. [Workflows and Agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents). Current LangGraph Python documentation.

[^43]: LangChain. [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence). Current LangGraph Python documentation.

[^44]: LangChain. [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts). Current LangGraph Python documentation.

[^45]: LightGBM contributors. [Features](https://lightgbm.readthedocs.io/en/stable/Features.html). Stable documentation.

[^46]: scikit-learn contributors. [TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html). Stable documentation.

[^47]: scikit-learn contributors. [Probability Calibration](https://scikit-learn.org/stable/modules/calibration.html). Stable documentation.

[^48]: Zhiyu Chen and coauthors / ACL Anthology. [FinQA: A Dataset of Numerical Reasoning over Financial Data](https://aclanthology.org/2021.emnlp-main.300/). November 2021, EMNLP.

[^49]: Pranab Islam and coauthors. [FinanceBench: A New Benchmark for Financial Question Answering](https://arxiv.org/abs/2311.11944). 20 November 2023.

[^50]: Local project evidence, inspected 11 September 2026: [finance-core.ts](C:/Users/admin/Desktop/fin-AAI/momentum-site/lib/finance-core.ts), [finance-paper.ts](C:/Users/admin/Desktop/fin-AAI/momentum-site/lib/finance-paper.ts), [finance-model.ts](C:/Users/admin/Desktop/fin-AAI/momentum-site/lib/finance-model.ts), [finance-market.ts](C:/Users/admin/Desktop/fin-AAI/momentum-site/lib/finance-market.ts), [finance-research.ts](C:/Users/admin/Desktop/fin-AAI/momentum-site/lib/finance-research.ts), [finance-seed.json](C:/Users/admin/Desktop/fin-AAI/momentum-site/lib/finance-seed.json), and [investment_policy.json](C:/Users/admin/Desktop/fin-AAI/config/investment_policy.json). Local code observations are not a deployment or live-credential attestation.

[^51]: NSE. [EOD / Historical Data Subscription](https://www.nseindia.com/static/market-data/eod-historical-data-subscription). Current product documentation.

[^52]: LangChain. [LangChain Overview](https://docs.langchain.com/oss/python/langchain/overview). Current Python documentation.
