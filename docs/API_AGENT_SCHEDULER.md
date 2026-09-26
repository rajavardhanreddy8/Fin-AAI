# API-agent scheduling

The Codex heartbeat has been removed. To use Windows Task Scheduler instead,
first set the provider variables from [API_AGENT_SETUP.md](API_AGENT_SETUP.md)
in the user or machine environment, then run PowerShell from the project root:

```powershell
.\scripts\register_finance_agent_tasks.ps1
```

This registers two weekday tasks at 08:30 and 17:00 local time. The tasks call
the local Python agent runner and inherit the caller-owned API-key environment.
No key is embedded in the task definition or command line.
