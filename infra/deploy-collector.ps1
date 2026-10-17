param(
    [string]$Profile = "fin-aai",
    [string]$Region = "ap-southeast-2",
    [string]$InstanceId = "i-0bb8f913a855766c7",
    [string]$SecretId = "arn:aws:secretsmanager:ap-southeast-2:933989369834:secret:BreezeCollectorSecret-4zDJPaWSgSUd-C9E3Zd",
    [string]$Bucket = "fin-aai-foundation-databucket-bficilpuii1y"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Encode-File([string]$Path) {
    [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((Get-Content -Raw -LiteralPath $Path)))
}

$files = @{
    "/opt/fin-aai/collector/src/stock_research/__init__.py" = Encode-File "$root/src/stock_research/__init__.py"
    "/opt/fin-aai/collector/src/stock_research/collectors/__init__.py" = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes('"""Data-only collector package."""'))
    "/opt/fin-aai/collector/src/stock_research/collectors/breeze_ohlcv.py" = Encode-File "$root/src/stock_research/collectors/breeze_ohlcv.py"
    "/opt/fin-aai/collector/run_breeze_collector.py" = Encode-File "$root/scripts/run_breeze_collector.py"
}

$commands = @(
    "dnf install -y python3-boto3",
    "install -d -m 750 /opt/fin-aai/collector/src/stock_research/collectors"
)
foreach ($destination in $files.Keys) {
    $commands += "printf '%s' '$($files[$destination])' | base64 -d > '$destination'"
}
$commands += @(
    "install -d -m 700 /etc/fin-aai",
    "printf '%s\n' 'AWS_REGION=$Region' 'AWS_DEFAULT_REGION=$Region' 'BREEZE_SECRET_ID=$SecretId' 'PILOT_DATA_BUCKET=$Bucket' 'PYTHONPATH=/opt/fin-aai/collector/src' > /etc/fin-aai/collector.env",
    "chmod 600 /etc/fin-aai/collector.env",
    "chmod 750 /opt/fin-aai/collector/run_breeze_collector.py"
)

$parameterFile = Join-Path ([IO.Path]::GetTempPath()) ("fin-aai-ssm-" + [guid]::NewGuid().ToString() + ".json")
$payload = @{ 
    DocumentName = "AWS-RunShellScript"
    InstanceIds = @($InstanceId)
    Parameters = @{ commands = $commands }
    Comment = "Deploy fin-AAI data-only Breeze collector"
}
[IO.File]::WriteAllText($parameterFile, ($payload | ConvertTo-Json -Compress -Depth 4), (New-Object Text.UTF8Encoding($false)))
try {
    & aws ssm send-command `
        --cli-input-json "file://$parameterFile" `
        --region $Region `
        --profile $Profile `
        --query "Command.CommandId" `
        --output text
}
finally {
    Remove-Item -LiteralPath $parameterFile -Force -ErrorAction SilentlyContinue
}
