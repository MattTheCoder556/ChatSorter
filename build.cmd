@echo off
REM Build a standalone ChatSorter.exe on Windows (output: dist\ChatSorter.exe).
REM Requires Python on PATH. Double-click, or run from a terminal.
pip install pyinstaller || goto :err
pyinstaller --noconfirm --onefile --windowed --name ChatSorter ^
  --hidden-import auto_sort --hidden-import watch_vault ^
  --hidden-import classify_vault --hidden-import sort_vault ^
  gui.py || goto :err
echo.
echo Done -> dist\ChatSorter.exe
pause
exit /b 0
:err
echo Build failed.
pause
exit /b 1
