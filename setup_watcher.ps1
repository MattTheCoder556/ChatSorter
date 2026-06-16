<#
  One-shot setup for the always-on vault watcher.
  RUN THIS YOURSELF in your own PowerShell window (it stores your API key and
  registers a Scheduled Task — actions that need your interactive rights).

      cd "C:\Users\Matt\Desktop\BlueskyAgent\ChatSorter"
      .\setup_watcher.ps1

  What it does:
    1. Reads your MiniMax key from Smart Composer's config (you never type it).
    2. Persists MINIMAX_API_KEY / MINIMAX_MODEL / MINIMAX_BASE_URL as USER env vars.
    3. Registers the "VaultWatch" Scheduled Task (starts at logon, auto-restarts).
    4. Starts it now.
  The watcher uses --ignore-existing, so your current files are left alone; only
  notes that arrive in the vault root from now on get auto-sorted.
#>
$ErrorActionPreference = "Stop"
$here  = $PSScriptRoot
$vault = "C:\Users\Matt\Desktop\BlueskyAgent\bluesky-agent\vault"
$cfg   = "$vault\.obsidian\plugins\smart-composer\data.json"

# 1. pull the key from Smart Composer config (not printed)
$data = Get-Content $cfg -Raw | ConvertFrom-Json
$key  = ($data.providers | Where-Object { $_.id -eq 'minimax' }).apiKey
if (-not $key) { throw "Couldn't find the MiniMax apiKey in $cfg" }

# 2. persist env vars for the unattended task
setx MINIMAX_API_KEY  "$key" | Out-Null
setx MINIMAX_MODEL    "MiniMax-M3" | Out-Null
setx MINIMAX_BASE_URL "https://api.minimax.io/v1" | Out-Null
# also set in THIS session so the task we start now can inherit them
$env:MINIMAX_API_KEY  = $key
$env:MINIMAX_MODEL    = "MiniMax-M3"
$env:MINIMAX_BASE_URL = "https://api.minimax.io/v1"
Write-Host "Stored MiniMax credentials (key length $($key.Length))." -ForegroundColor Green

# 3. register the Scheduled Task
& "$here\register_watcher.ps1" -Vault $vault -IgnoreExisting -Interval 5

# 4. start it now
Start-ScheduledTask -TaskName "VaultWatch"
Start-Sleep -Seconds 2
$info = Get-ScheduledTask -TaskName "VaultWatch" | Get-ScheduledTaskInfo
Write-Host "VaultWatch state: $((Get-ScheduledTask -TaskName 'VaultWatch').State); LastResult: $($info.LastTaskResult)" -ForegroundColor Green
Write-Host ""
Write-Host "Done. Drop a new .md into $vault root and it will auto-sort within ~5s."
Write-Host "Manage:  Stop-ScheduledTask -TaskName VaultWatch  |  Unregister-ScheduledTask -TaskName VaultWatch -Confirm:`$false"
