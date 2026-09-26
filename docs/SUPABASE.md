# Supabase backend

SQLite remains the default offline backend. The cloud schema is in
`supabase/migrations/202607180001_initial_stock_research.sql`.

Install the optional server-side client:

```powershell
python -m pip install -e .[supabase]
```

Copy `.env.example` to `.env.local` and set `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY` there. Do not commit `.env.local`; never expose the
service-role key to a browser. The service key is only for background ingestion
and connection checks. User-facing portfolio and watchlist operations must use
an authenticated user JWT so the database RLS policies apply.

To perform a live connection check after configuring the variables:

```powershell
$env:PYTHONPATH = "src"
python -m stock_research.cli check-supabase
```

To upload accepted evidence for a completed non-bank fixture after a local validation run:

```powershell
$env:PYTHONPATH = "src"
python -m stock_research.cli --db maruti-research.db sync-company-supabase tests/fixtures/maruti --run-pipeline --as-of 2026-07-18
```
