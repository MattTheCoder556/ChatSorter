@echo off
REM Double-click to STOP the vault watcher.
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*watch_vault.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo.
echo   VaultWatch is now OFF. New notes will no longer be sorted automatically.
echo.
timeout /t 4 >nul
