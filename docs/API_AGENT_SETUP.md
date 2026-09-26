# API-key agent runtime

The finance agents run as local Python processes and call an OpenAI-compatible
provider with a caller-owned API key. Codex is not the model runtime.

Set these variables in the machine's server-side environment:

```powershell
$env:RESEARCH_LLM_BASE_URL = "https://api.openai.com/v1"
$env:RESEARCH_LLM_API_KEY = "<provider key>"
$env:RESEARCH_LLM_MODEL = "<provider model>"
$env:RESEARCH_LLM_RPM = "10"
$env:RESEARCH_LLM_RPD = "100"
$env:RESEARCH_LLM_TPM = "60000"
$env:RESEARCH_LLM_TPD = "1000000"
```

The URL and model can point to another provider that supports the OpenAI
chat-completions JSON contract. The key is read only by the local process and
is never written to reports, prompts, the database, or the browser.

Run the agent system directly:

```powershell
python scripts/run_finance_agents.py --phase pre --db output/finance-automation.db
python scripts/run_finance_agents.py --phase post --db output/finance-automation.db
```

The deterministic market, screening, acquisition, forecast, and historical
evaluation agents work without an API key. Only the Research Specialists agent
requires the provider settings. The queue enforces the configured request and
token budgets and stores only model name, status, citations, and validated JSON
results.

## Configure a local research provider

The local specialist queue needs a caller-owned OpenAI-compatible provider. OpenRouter, Groq, and other compatible providers can be used by setting their base URL and model ID. Configure it interactively; the API key is hidden while entered and is stored only in the current Windows user's environment.

```powershell
.\scripts\configure_research_provider.ps1
python scripts\verify_finance_system.py
python scripts\run_finance_agents.py --phase pre --db output\finance-automation.db
```

The verifier reports only `set` or `missing`; it never prints the key. The scheduled tasks inherit the user environment after they are restarted or the next user session begins. Do not paste API keys into chat, reports, source files, or task arguments.
