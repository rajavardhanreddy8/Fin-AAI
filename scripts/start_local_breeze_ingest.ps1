param(
    [string]$FromAt,
    [string]$ToAt,
    [string]$Key,
    [string]$PaperBarOutput,
    [string]$HistoryFrom,
    [string]$HistoryTo,
    [string]$Bucket = "fin-aai-foundation-databucket-bficilpuii1y",
    [switch]$RetryMissing,
    [switch]$ResetBreezeAppCredentials
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
$credentialFile = Join-Path $projectRoot ".env.local"
$env:PYTHONPATH = Join-Path $projectRoot "src"
if (($HistoryFrom -or $HistoryTo) -and (-not $HistoryFrom -or -not $HistoryTo)) { throw "Supply both HistoryFrom and HistoryTo." }
if (-not $HistoryFrom -and (-not $FromAt -or -not $ToAt -or -not $Key)) { throw "Supply FromAt, ToAt and Key, or HistoryFrom and HistoryTo." }
python (Join-Path $PSScriptRoot "run_local_breeze_ingest.py") --check-connection
if ($LASTEXITCODE -ne 0) { Write-Warning "Breeze preflight could not resolve the server. Continuing with the collector's retries." }
aws sts get-caller-identity --profile fin-aai --region ap-southeast-2 --output json | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Refresh the fin-aai AWS sign-in, then rerun this script." }
function Read-SecretValue([string]$Prompt) {
    $secure = Read-Host $Prompt -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

if (Test-Path $credentialFile) {
    $userSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls.exe $credentialFile /inheritance:r /grant:r "*${userSid}:(F)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not restrict permissions on .env.local." }
    foreach ($line in Get-Content $credentialFile) {
        if ($line -match '^(BREEZE_API_KEY|BREEZE_API_SECRET)=(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
}
if ($ResetBreezeAppCredentials -or -not $env:BREEZE_API_KEY -or -not $env:BREEZE_API_SECRET) {
    $env:BREEZE_API_KEY = Read-SecretValue "Breeze App Key"
    $env:BREEZE_API_SECRET = Read-SecretValue "Breeze Secret Key"
    if (-not (Test-Path $credentialFile)) { New-Item -ItemType File -Path $credentialFile | Out-Null }
    $userSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls.exe $credentialFile /inheritance:r /grant:r "*${userSid}:(F)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not restrict permissions on .env.local; credentials were not saved." }
    [IO.File]::WriteAllLines($credentialFile, @(
        "BREEZE_API_KEY=$env:BREEZE_API_KEY",
        "BREEZE_API_SECRET=$env:BREEZE_API_SECRET"
    ), [Text.UTF8Encoding]::new($false))
}
$env:BREEZE_API_SESSION = Read-SecretValue "Fresh Breeze API session"
try {
    if ($HistoryFrom) {
        $historyArgs = @("--history-from", $HistoryFrom, "--history-to", $HistoryTo, "--bucket", $Bucket, "--aws-profile", "fin-aai", "--archive-dir", (Join-Path $projectRoot "output/market-data"), "--calendar-db", (Join-Path $projectRoot "output/finance-automation.db"))
        if ($RetryMissing) { $historyArgs += "--retry-missing" }
        python (Join-Path $PSScriptRoot "run_local_breeze_ingest.py") @historyArgs
    } else {
        $collectionArgs = @("--from-at", $FromAt, "--to-at", $ToAt, "--bucket", $Bucket, "--key", $Key, "--aws-profile", "fin-aai")
        if ($PaperBarOutput) { $collectionArgs += @("--paper-bar-output", $PaperBarOutput) }
        python (Join-Path $PSScriptRoot "run_local_breeze_ingest.py") @collectionArgs
    }
    if ($LASTEXITCODE -notin 0, 2) {
        throw "Local ingestion failed with exit code $LASTEXITCODE."
    }
    if ($LASTEXITCODE -eq 2) {
        Write-Warning "Ingestion completed with explicit invalid, missing, or calendar-gap exclusions; inspect output/market-data/collection-result.json."
    }
}
finally {
    Remove-Item Env:BREEZE_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:BREEZE_API_SECRET -ErrorAction SilentlyContinue
    Remove-Item Env:BREEZE_API_SESSION -ErrorAction SilentlyContinue
}
