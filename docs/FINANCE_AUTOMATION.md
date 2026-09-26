# fin-AAI daily automation

The local Windows Task Scheduler runs two weekday cycles in **Asia/Kolkata**: 8:30 AM before the NSE cash-market open, and 5:00 PM after the regular close. The task registration script is `scripts/register_finance_agent_tasks.ps1`; it invokes `scripts/run_finance_agents.py` and writes inspectable JSON reports under `output/`.

Each cycle checks the stored official exchange calendar and skips holidays and unsupported sessions. The pre-market cycle refreshes the official Nifty 500 membership and previous-session closing prices, freezes evidence, records coverage and research triggers, and creates prospective baseline forecasts only while the market is closed. The post-market cycle refreshes completed official closes and announcement metadata, scores forecasts against exact session prices, and reruns the read-only historical trading evaluation. It does not auto-queue paper orders or send broker orders.

The model queue runs only when a separate local provider configuration is present. Supported configuration is either the generic OpenAI-compatible `RESEARCH_LLM_*` variables or the opt-in Groq `GROQ_*` variables described in `docs/API_AGENT_SETUP.md`. Without local configuration, deterministic screening and scoring still run; the report records `configuration_required` for model work. Never put a key in this file, a task prompt, a report, or the browser.

For a secret-safe evidence snapshot, run:

```powershell
python scripts/verify_finance_system.py
```

The command prints Git state, test status, registered task names, provider-variable presence, the latest agent report, and the no-broker boundary. It never prints secret values. JSON reports are written under `output/finance-automation-YYYY-MM-DD-{pre,post}.json`; completed runs are not repeated.

The historical trading evaluator is a monitoring record, not a newly validated strategy. A production recommendation requires current-date source refresh, evidence readiness, walk-forward evaluation, and a separate paper-trading record. Real-money execution is not connected.
