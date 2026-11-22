@echo off
:: Double-click to open the AEGIS web app in your browser.
:: Run install.bat once first. Close this window (or press Ctrl+C) to stop AEGIS.
cd /d "%~dp0"

if not exist ".venv\Scripts\aegis.exe" (
    echo AEGIS is not installed yet. Run install.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
aegis ui
if %ERRORLEVEL% neq 0 pause
