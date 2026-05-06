@echo off
setlocal enabledelayedexpansion

echo ================================================
echo   AEGIS Academic Integrity Checker - Installer
echo ================================================
echo.

:: Check Python
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found. Install Python 3.9+ from https://python.org
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

:: Choose install mode
echo.
echo Install mode:
echo   1. Minimal  - core only, no ML models (~200 MB)
echo   2. Full     - all detectors, ML models (~2 GB download)
echo   3. Docker   - skip Python install, use Docker instead
echo.
set /p CHOICE="Enter 1, 2, or 3 [default: 1]: "
if "%CHOICE%"=="" set CHOICE=1

if "%CHOICE%"=="1" (
    echo [..] Installing core dependencies...
    pip install -e . --quiet
    if !ERRORLEVEL! neq 0 goto :installerror
    echo [OK] Core installation complete.
)

if "%CHOICE%"=="2" (
    echo [..] Installing all dependencies (this may take 5-15 minutes)...
    pip install -e ".[ml,nlp,bib]" --quiet
    if !ERRORLEVEL! neq 0 goto :installerror
    echo [..] Downloading spaCy English model...
    python -m spacy download en_core_web_sm
    echo [OK] Full installation complete.
)

if "%CHOICE%"=="3" (
    docker --version >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Docker not found. Install Docker Desktop from https://docker.com
        pause
        exit /b 1
    )
    echo [..] Building and starting AEGIS with Docker...
    docker compose up --build -d
    echo [OK] AEGIS API running at http://localhost:8000
    echo      Swagger UI: http://localhost:8000/docs
    pause
    exit /b 0
)

:: Copy .env if missing
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [OK] Created .env from template. Edit it to set your email for Crossref API.
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
echo   Installation complete!
echo ================================================
echo.
echo Quick start:
echo   aegis analyze paper.pdf --html report.html
echo   aegis serve --port 8000
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
