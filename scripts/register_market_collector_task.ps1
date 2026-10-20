[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$ProjectRoot = "C:\Users\admin\Desktop\fin-AAI"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
try { $python = (Get-Command python -ErrorAction Stop).Source }
catch { throw "python is not on PATH; install Python 3.13 before registering the local collector." }
$registryPath = Join-Path $ProjectRoot "config\market-news-sources.json"
$registry = Get-Content -LiteralPath $registryPath -Raw | ConvertFrom-Json
if ($registry.Count -ne 1 -or $registry[0].source_id -ne "pib_press_releases" -or $registry[0].url -ne "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3" -or $registry[0].permitted -ne $true) {
    throw "The collector task only accepts the single permitted PIB source registry."
}
$intervalSeconds = [int]$registry[0].polling_interval
if ($intervalSeconds -lt 60 -or $intervalSeconds % 60 -ne 0) {
    throw "The registry polling interval must be at least one minute and divisible by one minute."
}
$pythonVersion = & $python --version 2>&1
if ($LASTEXITCODE -ne 0 -or $pythonVersion -notmatch '^Python 3\.13\.') {
    throw "The Python launcher must resolve Python 3.13. Detected: $pythonVersion"
}

$taskName = "fin-AAI local market news collector"
$arguments = "scripts\run_market_ingest.py --feed-registry config\market-news-sources.json --output output\market-news --refresh"
$nextHour = (Get-Date).Date.AddHours((Get-Date).Hour + 1)
$trigger = New-ScheduledTaskTrigger -Once -At $nextHour -RepetitionInterval ([TimeSpan]::FromSeconds($intervalSeconds)) -RepetitionDuration ([TimeSpan]::FromDays(3650))
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $ProjectRoot
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
if ($PSCmdlet.ShouldProcess($taskName, "Register hourly local PIB market-news collector")) {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Collect only the permitted PIB RSS source into local market-news evidence; no models or trading." -Force | Out-Null
    Write-Output "Registered $taskName every $intervalSeconds seconds."
} else {
    Write-Output "Preview task: $taskName"
    Write-Output "Action: $python $arguments"
    Write-Output "Working directory: $ProjectRoot"
    Write-Output "Interval seconds: $intervalSeconds"
}
