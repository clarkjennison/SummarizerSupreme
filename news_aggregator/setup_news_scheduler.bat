@echo off
REM ============================================================
REM  setup_news_scheduler.bat
REM  One-time setup: venv, dependencies, Task Scheduler job
REM  for the Healthcare VC News Aggregator (8 AM ET, Mon-Fri).
REM  Run AFTER setting up daily_summary (shares Gmail credentials).
REM ============================================================

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set VENV_DIR=%SCRIPT_DIR%venv
set LOG_DIR=%SCRIPT_DIR%logs
set TASK_NAME=HealthcareVCNewsBot

echo ============================================================
echo  Healthcare VC News Aggregator — Setup
echo ============================================================
echo.

REM ---- Check Python --------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from python.org.
    pause & exit /b 1
)

REM ---- Virtual environment -------------------------------------------
if exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [OK] Virtual environment already exists.
) else (
    echo Creating virtual environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (echo ERROR: venv creation failed. & pause & exit /b 1)
    echo [OK] Virtual environment created.
)

REM ---- Dependencies --------------------------------------------------
echo Installing dependencies...
call "%VENV_DIR%\Scripts\activate.bat"
pip install --quiet --upgrade pip
pip install --quiet -r "%SCRIPT_DIR%requirements.txt"
if errorlevel 1 (echo ERROR: pip install failed. & pause & exit /b 1)
echo [OK] Dependencies installed.

REM ---- Logs directory ------------------------------------------------
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
echo [OK] Logs directory ready.

REM ---- .env check ----------------------------------------------------
if not exist "%SCRIPT_DIR%.env" (
    echo.
    echo WARNING: .env file not found.
    echo Copy .env.example to .env and fill in your values.
    echo.
    pause & exit /b 1
)
echo [OK] .env file found.

REM ---- Test run (no email) ------------------------------------------
echo.
echo Running test (no email sent)...
python "%SCRIPT_DIR%main.py" --test
if errorlevel 1 (
    echo ERROR: Test run failed. Check your .env settings.
    pause & exit /b 1
)

REM ---- Register Task Scheduler task ----------------------------------
echo.
echo Registering scheduled task "%TASK_NAME%"...

schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "\"%SCRIPT_DIR%run_news.bat\"" ^
    /sc WEEKLY ^
    /d MON,TUE,WED,THU,FRI ^
    /st 08:00 ^
    /ru "%USERNAME%" ^
    /rl LIMITED ^
    /f

if errorlevel 1 (
    echo WARNING: Scheduled task could not be created automatically.
    echo Set it up manually in Task Scheduler:
    echo   Action:  "%SCRIPT_DIR%run_news.bat"
    echo   Trigger: Daily at 8:00 AM, Mon-Fri
) else (
    echo [OK] Task "%TASK_NAME%" registered — runs Mon-Fri at 8:00 AM.
)

echo.
echo ============================================================
echo  Setup complete!
echo.
echo  Test now:     python main.py --test
echo  Send now:     python main.py
echo  Logs:         %LOG_DIR%\news_aggregator.log
echo ============================================================
echo.
pause
