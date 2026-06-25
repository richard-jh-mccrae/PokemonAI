<#
.SYNOPSIS
  Register (or refresh) the daily Windows Scheduled Task for the Pokemon TCG meta tracker.

.EXAMPLE
  pwsh -File tools/meta_tracker/register_task.ps1 -Time 03:30

.NOTES
  The task runs as the current user. Provide Kaggle credentials so the CLI can
  authenticate non-interactively, preferably via the user profile token file:
      mkdir $env:USERPROFILE\.kaggle
      Set-Content $env:USERPROFILE\.kaggle\access_token 'KGAT_xxx'
  (KAGGLE_API_TOKEN as a *user* environment variable also works.)
#>
param(
  [string]$Time = "03:30",
  [string]$TaskName = "PokemonMetaTracker",
  [string]$Bands = "",          # e.g. "Elite High"; empty = all bands
  [int]$Cap = 0                 # 0 = use config.DAILY_EPISODE_CAP
)
$ErrorActionPreference = "Stop"

$repo   = (Resolve-Path "$PSScriptRoot\..\..").Path
$python = (Get-Command python).Source
$script = Join-Path $repo "tools\run_meta_tracker.py"

$args = "`"$script`""
if ($Bands) { $args += " --bands $Bands" }
if ($Cap -gt 0) { $args += " --cap $Cap" }

$action   = New-ScheduledTaskAction -Execute $python -Argument $args -WorkingDirectory $repo
$trigger  = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
              -ExecutionTimeLimit (New-TimeSpan -Hours 3)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
  -Description "Daily Pokemon TCG deck-meta scrape + dashboard" -Force | Out-Null

Write-Host "Registered '$TaskName' daily at $Time."
Write-Host "Dashboard will refresh at: $repo\reports\meta_dashboard.html"
Write-Host "Reminder: ensure $env:USERPROFILE\.kaggle\access_token (or user KAGGLE_API_TOKEN) is set."
