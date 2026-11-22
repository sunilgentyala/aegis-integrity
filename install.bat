@echo off
setlocal enabledelayedexpansion

:: Always operate from this script's own directory, regardless of
:: where it was invoked from (e.g. double-clicked, or run via a
:: shortcut/PATH from a different working directory).
cd /d "%~dp0"

echo ================================================
echo   AEGIS Academic Integrity Checker - Offline Setup
echo ================================================
echo.

:: Check Python
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Found Python %PYVER%

:: Create virtual environment
if not exist ".venv" (
    echo [..] Creating virtual environment...
    python -m venv .venv
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment already exists.
)

:: Activate
call .venv\Scripts\activate.bat

:: Upgrade pip silently
echo [..] Upgrading pip...
python -m pip install --upgrade pip --quiet

:: Core-only install: no ML models, no extra downloads
echo [..] Installing core dependencies (~200 MB, no ML models)...
pip install -e . --quiet
if !ERRORLEVEL! neq 0 goto :installerror
echo [OK] Core installation complete.

:: Copy .env if missing
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [OK] Created .env from template.
    )
)

:: Verify install
echo [..] Verifying installation...
aegis --help >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARN] 'aegis' command not found on PATH. Use: .venv\Scripts\aegis
) else (
    echo [OK] 'aegis' command is ready.
)

echo.
echo ================================================
echo   Setup complete - runs fully offline.
echo ================================================
echo.
echo   Core checks (plagiarism, stylometry, watermark,
echo   n-gram) need no network access or model downloads.
echo   AI-detection ML models and citation lookups are
echo   optional extras - see README for:
echo     pip install -e ".[ml,nlp,bib]"
echo.
echo Quick start:
echo   Double-click start-aegis.bat   (opens the web app in your browser)
echo   aegis doctor                   (shows which checks are ready)
echo   aegis analyze paper.pdf --html report.html
echo.
echo To activate the environment next time:
echo   .venv\Scripts\activate
echo.
pause
exit /b 0

:installerror
echo [ERROR] pip install failed. See output above.
pause
exit /b 1
