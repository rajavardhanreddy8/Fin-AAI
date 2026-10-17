[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)][string]$RunId,
    [string]$ProjectRoot = "C:\Users\admin\Desktop\fin-AAI",
    [string]$Handoff = "output\paper-handoff\completed-bar.json",
    [string]$PilotDb = "output\intraday-pilot.db",
    [string]$ForwardDb = "output\intraday-forward.db",
    [string]$PolicyVersion,
    [string]$PythonPath
)

$ErrorActionPreference = "Stop"
$python = if ($PythonPath) {
    (Resolve-Path -LiteralPath $PythonPath).Path
} else {
    try { (Get-Command python -ErrorAction Stop).Source }
    catch { throw "python is not on PATH; pass -PythonPath with the intended interpreter." }
}
$policyArgs = if ($PolicyVersion) { " --policy-db $PilotDb --policy-version $PolicyVersion" } else { "" }
$startArgs = "scripts\run_intraday_paper.py --start --run-id $RunId --state-db $ForwardDb --calendar-db output\finance-automation.db --assumptions config\intraday-paper-assumptions.json$policyArgs"
$consumerArgs = "scripts\run_paper_session.py --bar $Handoff --run-id $RunId --state-db $ForwardDb --review-pilot-db $PilotDb$policyArgs"
$reviewArgs = "-m stock_research.cli pilot-status --pilot-db $PilotDb --forward-db $ForwardDb"
$days = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
if ($PSCmdlet.ShouldProcess("fin-AAI local paper tasks", "Register start, consumer and read-only review")) {
    $start = New-ScheduledTaskAction -Execute $python -Argument $startArgs -WorkingDirectory $ProjectRoot
    $consumer = New-ScheduledTaskAction -Execute $python -Argument $consumerArgs -WorkingDirectory $ProjectRoot
    $review = New-ScheduledTaskAction -Execute $python -Argument $reviewArgs -WorkingDirectory $ProjectRoot
    $startTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At 9:10AM
    $consumeTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At 9:20AM
    $consumeTrigger.Repetition.Interval = "PT5M"
    $consumeTrigger.Repetition.Duration = "PT6H10M"
    $reviewTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At 3:45PM
    Register-ScheduledTask -TaskName "fin-AAI intraday paper start" -Action $start -Trigger $startTrigger -Description "Freezes the local forward-paper run before NSE open; no broker execution." -Force | Out-Null
    Register-ScheduledTask -TaskName "fin-AAI intraday paper consumer" -Action $consumer -Trigger $consumeTrigger -Description "Consumes only admitted local paper-bar handoffs; no broker execution." -Force | Out-Null
    Register-ScheduledTask -TaskName "fin-AAI intraday paper review" -Action $review -Trigger $reviewTrigger -Description "Read-only post-session paper review; never promotes a policy." -Force | Out-Null
    Write-Output "Registered local paper start, consumer and read-only review tasks. Collector credential bootstrap remains manual."
} else {
    Write-Output "Preview start: $python $startArgs"
    Write-Output "Preview consumer: $python $consumerArgs"
    Write-Output "Preview review: $python $reviewArgs"
}
