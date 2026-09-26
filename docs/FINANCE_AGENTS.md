# fin-AAI specialist agents

The weekday heartbeat dispatches `scripts/run_finance_agents.py`. It invokes one
orchestrator, which records every agent's result in the daily JSON report. The
orchestrator is the scheduler boundary; it does not make a trade or change a
strategy rule.

| Agent | Responsibility | Output |
|---|---|---|
| Market Evidence | Refresh official Nifty constituent closes and post-market announcement metadata. | Price-session provenance and announcement count. |
| Evidence Screening | Freeze each constituent's evidence packet and record coverage, gaps, and research triggers. | Coverage counts and a screening run ID. |
| Forecast Measurement | Create pre-open baseline forecasts, or score prior forecasts after close. | Issued forecasts or outcome metrics. |
| Research Specialists | Consume verified frozen packets through the bounded model-work queue. | Queue state and completed specialist reviews. |
| Trading Evaluation | Re-run the existing read-only historical strategy evaluator after close. | Promotion gate and per-symbol historical evidence. |

Each agent receives a shared, typed context: phase, official exchange calendar,
session date, member snapshot, database location, model-call budget, and
evaluation flag. Every result identifies the responsible agent, a status,
structured output, and explicit errors. The orchestrator persists this audit
trail in `output/finance-automation-YYYY-MM-DD-{pre,post}.json`.

The research-specialist agent needs separate local Groq runtime configuration.
Without it, the other four roles still run deterministically and report
`configuration_required` for model work. The paper ledger remains in the
authenticated Momentum site and is not changed by these local agents.
