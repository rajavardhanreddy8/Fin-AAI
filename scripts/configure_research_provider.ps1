<#
.SYNOPSIS
  Configure a caller-owned OpenAI-compatible research provider for fin-AAI.
.DESCRIPTION
  Prompts for provider settings and stores them in the current Windows user's
  environment. The API key is entered as a secure prompt and is never echoed.
  This script does not call the provider or write a key into the repository.
#>
[CmdletBinding()]
param(
  [string]$BaseUrl,
  [string]$Model,
  [int]$RequestsPerMinute = 10,
  [int]$RequestsPerDay = 100,
  [int]$TokensPerMinute = 60000,
  [int]$TokensPerDay = 1000000
)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($BaseUrl)) { $BaseUrl = Read-Host 'Provider base URL (for example https://openrouter.ai/api/v1)' }
if ([string]::IsNullOrWhiteSpace($Model)) { $Model = Read-Host 'Provider model ID' }
$keySecure = Read-Host 'Provider API key (hidden)' -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($keySecure)
try { $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
if ([string]::IsNullOrWhiteSpace($BaseUrl) -or [string]::IsNullOrWhiteSpace($Model) -or [string]::IsNullOrWhiteSpace($key)) { throw 'Base URL, model, and API key are required.' }
$limits = @{
  RESEARCH_LLM_BASE_URL = $BaseUrl.TrimEnd('/')
  RESEARCH_LLM_API_KEY = $key
  RESEARCH_LLM_MODEL = $Model
  RESEARCH_LLM_RPM = [string]$RequestsPerMinute
  RESEARCH_LLM_RPD = [string]$RequestsPerDay
  RESEARCH_LLM_TPM = [string]$TokensPerMinute
  RESEARCH_LLM_TPD = [string]$TokensPerDay
}
foreach ($pair in $limits.GetEnumerator()) { [Environment]::SetEnvironmentVariable($pair.Key, $pair.Value, 'User'); Set-Item -Path "Env:$($pair.Key)" -Value $pair.Value }
$key = $null
Write-Output "Configured $($limits.RESEARCH_LLM_MODEL) at $($limits.RESEARCH_LLM_BASE_URL) for this user. Restart scheduled tasks or terminals before running agents."
