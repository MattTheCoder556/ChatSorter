<#
  Register a Windows Scheduled Task that runs watch_vault.py at logon and keeps
  it running, so any .md dropped into the vault root is sorted automatically.

  Run in PowerShell (no admin needed for a per-user task). Examples:
    .\register_watcher.ps1 -Vault "C:\Users\Matt\knowledge-vault\wiki"
    .\register_watcher.ps1 -Vault "C:\Users\Matt\my-vault\wiki" -Name "MyVaultWatch"
    .\register_watcher.ps1 -Vault "C:\Users\Matt\knowledge-vault\wiki" -NoLlm

  Requires:
    * Python on PATH.
    * watch_vault.py, classify_vault.py, sort_vault.py next to this script.
    * MINIMAX_API_KEY (and MINIMAX_MODEL) set as USER environment variables:
        setx MINIMAX_API_KEY "your-key-here"
        setx MINIMAX_MODEL   "MiniMax-M2"   # or your exact M3 model id

  Manage it:
    Start-ScheduledTask     -TaskName "VaultWatch"          # start now
    Stop-ScheduledTask      -TaskName "VaultWatch"          # stop the watcher
    Unregister-ScheduledTask -TaskName "VaultWatch" -Confirm:$false   # remove
#>
param(
    [Parameter(Mandatory = $true)][string]$Vault,
    [string]$Name   = "VaultWatch",
    [string]$Script = "$PSScriptRoot\watch_vault.py",
    [double]$Interval = 5,
    [switch]$NoLlm,
    [switch]$IgnoreExisting
)

# prefer pythonw.exe (no console window) for a background watcher; fall back to python
$py = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $py) { $py = (Get-Command python3 -ErrorAction SilentlyContinue).Source }
if (-not $py) { throw "Python not found on PATH. Install Python and retry." }
if (-not (Test-Path $Script)) { throw "watch_vault.py not found at $Script" }

$argline = "`"$Script`" `"$Vault`" --interval $Interval"
if ($NoLlm) { $argline += " --no-llm" }
if ($IgnoreExisting) { $argline += " --ignore-existing" }

$action  = New-ScheduledTaskAction -Execute $py -Argument $argline
$trigger = New-ScheduledTaskTrigger -AtLogOn
# keep it alive: no time limit, restart if it ever exits
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger `
    -Settings $settings -Description "Watch + auto-sort $Vault" -Force | Out-Null

Write-Host "Registered watcher '$Name' for '$Vault' (starts at logon)."
Write-Host "Start it now: Start-ScheduledTask -TaskName '$Name'"
