@echo off
REM Double-click to CHECK whether the watcher is running + see recent activity.
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*watch_vault.py*' }; if ($p) { Write-Host ''; Write-Host '  VaultWatch: RUNNING (PID' $p.ProcessId ')' -ForegroundColor Green } else { Write-Host ''; Write-Host '  VaultWatch: STOPPED' -ForegroundColor Red; Write-Host '  (double-click watch.cmd to start it)' }; $log = Join-Path '%~dp0' 'vaultwatch.log'; if (Test-Path $log) { Write-Host ''; Write-Host '  --- recent activity ---' -ForegroundColor Cyan; Get-Content $log -Tail 15 | ForEach-Object { Write-Host ('  ' + $_) } } else { Write-Host '  (no activity yet)' }; Write-Host ''"
pause
