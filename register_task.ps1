<#
  Register a Windows Scheduled Task that classifies (MiniMax M3) + sorts a vault
  on an interval. Run in PowerShell (no admin needed for a per-user task).

  Examples:
    .\register_task.ps1 -Vault "C:\Users\Matt\knowledge-vault\wiki"
    .\register_task.ps1 -Vault "C:\Users\Matt\my-vault\wiki" -Minutes 5 -Name "MyVaultSort"
    .\register_task.ps1 -Vault "C:\Users\Matt\knowledge-vault\wiki" -NoLlm   # sort only

  Requires:
    * Python on PATH.
    * auto_sort.py, classify_vault.py, sort_vault.py all next to this script.
    * MINIMAX_API_KEY set as a USER environment variable (so the task can read it):
        setx MINIMAX_API_KEY "your-key-here"
        setx MINIMAX_MODEL   "MiniMax-M2"   # or your exact M3 model id
      (open a NEW terminal after setx so the value is picked up.)

  Remove later with: Unregister-ScheduledTask -TaskName "VaultSort" -Confirm:$false
#>
param(
    [Parameter(Mandatory = $true)][string]$Vault,
    [int]$Minutes = 10,
    [string]$Name   = "VaultSort",
    [string]$Script = "$PSScriptRoot\auto_sort.py",
    [switch]$NoLlm
)

# locate python
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command python3 -ErrorAction SilentlyContinue).Source }
if (-not $py) { throw "Python not found on PATH. Install Python and retry." }
if (-not (Test-Path $Script)) { throw "auto_sort.py not found at $Script" }

$argline = "`"$Script`" `"$Vault`""
if ($NoLlm) { $argline += " --no-llm" }

$action  = New-ScheduledTaskAction -Execute $py -Argument $argline
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes $Minutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger `
    -Settings $settings -Description "Classify+sort $Vault every $Minutes min" -Force | Out-Null

Write-Host "Registered task '$Name': classify+sort '$Vault' every $Minutes minute(s)."
Write-Host "Run now to test: Start-ScheduledTask -TaskName '$Name'"
Write-Host "Inspect last run: (Get-ScheduledTaskInfo -TaskName '$Name')"
