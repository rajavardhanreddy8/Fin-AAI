# fin-AAI — Evidence-backed Indian Stock Research Agent

This repository is building a research agent that collects attributable Indian-market evidence, validates freshness and coverage, computes financial metrics deterministically, and asks a configured large language model (LLM) for a cited research recommendation. It never places orders. SQLite is the offline source of truth; accepted evidence can be synchronized to Supabase.

The evidence foundation is working. The provider-independent recommendation path is implemented and tested with a fake model, but live LLM inference remains unverified until the intended API provider, base URL, and model are confirmed and configured server-side.

## Research-ready pilots

The manifest-driven pipeline currently covers all ten configured securities. At
the fixture capture date, eight pass every readiness gate; NTPC and ICICI Bank
remain deliberately blocked because their latest accepted annual periods do not
have matching annual-report evidence.

- Tata Consultancy Services (`INE467B01029`)
- Infosys (`INE009A01021`)
- Reliance Industries (`INE002A01018`)
- ITC (`INE154A01025`)
- Maruti Suzuki India (`INE585B01010`)
- Larsen & Toubro (`INE018A01030`)
- Sun Pharmaceutical Industries (`INE044A01036`)
- NTPC (`INE733E01010`)
- HDFC Bank (`INE040A01034`)
- ICICI Bank (`INE090A01021`)

Each completed company has:

- verified NSE and BSE identifiers;
- 8 quarterly periods and 3 financial years of normalized results;
- annual-report and shareholding-pattern evidence;
- recent EOD prices;
- deterministic governance flags;
- source-document linkage for every accepted financial fact;
- idempotent local ingestion and server synchronization.

The fixture manifest contains captured, attributed evidence from official company/NSE sources and a named reputable price source. It is deterministic for regression testing; collectors may also read HTTP(S) manifests.

## Run locally on Windows PowerShell

```powershell
cd C:\Users\admin\Desktop\fin-AAI
$env:PYTHONPATH = "src"

python -m unittest discover -s tests -v
python -m stock_research.cli --db research.db company-pipeline tests/fixtures/tcs
python -m stock_research.cli --db research.db company-pipeline tests/fixtures/infosys
python -m stock_research.cli --db research.db company-pipeline tests/fixtures/reliance
python -m stock_research.cli --db research.db company-pipeline tests/fixtures/itc --as-of 2026-07-18
python -m stock_research.cli --db research.db company-pipeline tests/fixtures/maruti --as-of 2026-07-18
python -m stock_research.cli --db research.db weekly-changes `
  --window-start 2026-07-07 --as-of 2026-07-18
python -m stock_research.cli --db research.db weekly-universe `
  --window-start 2026-08-25 --as-of 2026-09-01 `
  --refresh-nse-eod --refresh-nse-shareholding `
  --refresh-company-annual-reports
```

For a fresh run, execute `weekly-universe` with the refresh switches first. Then generate one recommendation from the accepted local evidence:

```powershell
$env:RESEARCH_LLM_BASE_URL = "https://PROVIDER.example/v1"
$env:RESEARCH_LLM_API_KEY = "SERVER_ONLY_SECRET"
$env:RESEARCH_LLM_MODEL = "PROVIDER_MODEL_ID"

python -m stock_research.cli --db research.db research-recommendation `
  tests/fixtures/infosys --as-of 2026-09-06 `
  --output output/infosys-research.md
```

The adapter expects the OpenAI-compatible chat-completions JSON shape. Do not assume a provider from a nickname such as “Croc API”; verify its official base URL and model identifier first. If readiness fails, the command writes an `insufficient_evidence` report and does not call the LLM.

Each company pipeline exits with code `2` if a research-readiness requirement is incomplete. TCS and Infosys each contain 44 accepted financial facts; Reliance, ITC, and Maruti each contain 33 facts using their company-reported taxonomies. Every completed non-bank pilot contains eight complete quarters, three complete financial years, and ten recent price sessions.

## Supabase synchronization

Apply the SQL files in `supabase/migrations` in order. Research tables have RLS enabled and no end-user policies; only the server-side service client can ingest shared evidence. Portfolio and watchlist rows retain their user-owned policies.

Install the optional client and set secrets only for the current server-side PowerShell session:

```powershell
python -m pip install -e ".[supabase]"
$env:SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY = "YOUR_SERVER_ONLY_SECRET"

python -m stock_research.cli check-supabase
python -m stock_research.cli --db tcs-research.db sync-tcs-supabase --run-pilot
python -m stock_research.cli --db maruti-research.db sync-company-supabase tests/fixtures/maruti --run-pipeline --as-of 2026-07-18
python -m stock_research.cli --db research.db weekly-universe `
  --window-start 2026-08-25 --as-of 2026-09-01 `
  --refresh-nse-eod --refresh-nse-shareholding `
  --refresh-company-annual-reports --sync-supabase
```

Never commit `.env.local`, a service-role key, broker credentials, or live database files. See `.env.example` for variable names only.

## Current scope

The full ten-company manifest exists, including a separate banking metric taxonomy.
Fixture prices are captured evidence. `--refresh-nse-eod` downloads recent official
NSE CM-UDiFF common bhavcopies and retains SQLite as the local evidence store. Use
the current run date as `--as-of` so stale prices correctly block synchronization.
`--refresh-nse-shareholding` discovers each latest NSE filing and downloads the
linked original NSE XBRL, whose embedded ISIN is validated before acceptance.
`--refresh-company-annual-reports` downloads the configured FY2026 NTPC and ICICI
Bank reports from their official investor pages, verifies company identity from
PDF text, and records the binary SHA-256 hash.
The checked-in fixtures are deterministic regression evidence, not a claim of live market data. A production recommendation must be preceded by a current-date refresh and readiness check. Model output is schema-validated, positive actions require deterministic valuation evidence and no blocking governance flag, every claim must cite a supplied document ID, and accepted recommendations are appended to the immutable ledger.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the wider phased design.

## Current verification workflow

From the project root, run the full cross-layer audit:

```powershell
python scripts\verify_finance_system.py --full
```

The audit checks the Python research suite, investing and trading workstream suites, the Momentum production build and application tests, registered weekday agent tasks, provider-variable presence, Git state, and the latest automation report. It never prints secret values. The JSON result is written to `output/finance-system-full-verification.json`.

To configure a caller-owned OpenAI-compatible provider without putting a key in chat or source files:

```powershell
.\scripts\configure_research_provider.ps1
```

Visible current artifacts include `output/current-universe.json`, `output/itc-current-evidence.md`, `output/trading-evaluation-2026-09-26.json`, and `output/finance-system-full-verification.json`. These reports distinguish evidence readiness, model availability, historical simulation, paper trading, and real-money execution.
