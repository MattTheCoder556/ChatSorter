@echo off
REM Double-click to START the vault watcher (runs hidden, notifies on each sort).
start "" pythonw "%~dp0watch_vault.py" "C:\Users\Matt\Desktop\BlueskyAgent\bluesky-agent\vault" --interval 5 --notify --model MiniMax-M3 --sc-config "C:\Users\Matt\Desktop\BlueskyAgent\bluesky-agent\vault\.obsidian\plugins\smart-composer\data.json"
echo.
echo   VaultWatch is now ON.
echo   Drop any .md into your vault root and it sorts itself within ~5 seconds.
echo   You'll get a desktop notification each time a note is filed.
echo.
echo   (Double-click "stop.cmd" to turn it off, "status.cmd" to check it.)
echo.
timeout /t 4 >nul
