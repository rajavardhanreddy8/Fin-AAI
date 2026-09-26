param(
    [string]$ProjectRoot = "C:\Users\admin\Desktop\fin-AAI"
)

$ErrorActionPreference = "Stop"
$python = (Get-Command python).Source
$days = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
$actionPre = New-ScheduledTaskAction -Execute $python -Argument "scripts\run_finance_agents.py --phase pre --db output\finance-automation.db" -WorkingDirectory $ProjectRoot
$actionPost = New-ScheduledTaskAction -Execute $python -Argument "scripts\run_finance_agents.py --phase post --db output\finance-automation.db" -WorkingDirectory $ProjectRoot
$triggerPre = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At 8:30AM
$triggerPost = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At 5:00PM

Register-ScheduledTask -TaskName "fin-AAI API agents pre-market" -Action $actionPre -Trigger $triggerPre -Description "Run fin-AAI specialist agents with caller-owned API keys before NSE open." -Force | Out-Null
Register-ScheduledTask -TaskName "fin-AAI API agents post-market" -Action $actionPost -Trigger $triggerPost -Description "Run fin-AAI specialist agents with caller-owned API keys after NSE close." -Force | Out-Null
Write-Output "Registered Windows tasks for weekdays at 08:30 and 17:00 local time."

