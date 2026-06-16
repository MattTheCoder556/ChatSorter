@echo off
REM Double-click to launch the ChatSorter desktop UI (Windows).
REM Uses pythonw so no console window appears behind the UI.
start "" pythonw "%~dp0gui.py"
