@echo off
REM ============================================================
REM  setup_scheduler.bat
REM
REM  Run this ONCE to:
REM    1. Create a Python virtual environment
REM    2. Install all dependencies
REM    3. Register a Windows Task Scheduler job that runs
REM       the daily summary bot at 5:30 PM Eastern every weekday
REM
REM  Run as your normal user (no admin rights needed for
REM  per-user scheduled tasks).
REM ============================================================

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set VENV_DIR=%SCRIPT_DIR%venv
set LOG_DIR=%SCRIPT_DIR%logs
set TASK_NAME=DailySummaryBot

echo ============================================================
echo  Daily Summary Bot — Setup
echo ============================================================
echo.

REM ---- 1. Check Python -----------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.11+ from python.org
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK] Python %PY_VER% found.

REM ---- 2. Create virtual environment ---------------------------------
if exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [OK] Virtual environment already exists.
) else (
    echo Creating virtual environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
)

REM ---- 3. Install dependencies ----------------------------------------
echo Installing dependencies (this may take a minute)...
call "%VENV_DIR%\Scripts\activate.bat"
pip install --quiet --upgrade pip
pip install --quiet -r "%SCRIPT_DIR%requirements.txt"
if errorlevel 1 (
    echo ERROR: pip install failed. Check your internet connection.
    pause
    exit /b 1
)
echo [OK] Dependencies installed.

REM ---- 4. Create logs directory ---------------------------------------
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
echo [OK] Logs directory ready at %LOG_DIR%

REM ---- 5. Verify .env file -------------------------------------------
if not exist "%SCRIPT_DIR%.env" (
    echo.
    echo WARNING: .env file not found!
    echo Please copy .env.example to .env and fill in your credentials before continuing.
    echo.
    pause
    exit /b 1
)
echo [OK] .env file found.

REM ---- 6. Run auth check (opens browser for Gmail OAuth) --------------
echo.
echo Running authentication check...
echo A browser window will open for Gmail. Sign in and grant access.
echo.
python "%SCRIPT_DIR%main.py" --auth
if errorlevel 1 (
    echo ERROR: Authentication failed. Check credentials and try again.
    pause
    exit /b 1
)

REM ---- 7. Register Windows Task Scheduler task ------------------------
echo.
echo Registering scheduled task "%TASK_NAME%"...

REM Delete existing task if present (ignore error if it doesn't exist)
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

REM Create the task:
REM   - Runs every weekday (Mon–Fri) at 17:30 (5:30 PM)
REM   - Uses the current logged-in user
REM   - Runs even if on battery
REM   - Starts in the script directory so relative paths work
schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "\"%SCRIPT_DIR%run.bat\"" ^
    /sc WEEKLY ^
    /d MON,TUE,WED,THU,FRI ^
    /st 17:30 ^
    /ru "%USERNAME%" ^
    /rl LIMITED ^
    /f

if errorlevel 1 (
    echo.
    echo WARNING: Could not create scheduled task automatically.
    echo You can set it up manually in Task Scheduler:
    echo   Action:    "%SCRIPT_DIR%run.bat"
    echo   Trigger:   Daily at 5:30 PM, weekdays
    echo.
) else (
    echo [OK] Scheduled task "%TASK_NAME%" registered successfully.
    echo      It will run Mon-Fri at 5:30 PM.
)

REM ---- 8. Done --------------------------------------------------------
echo.
echo ============================================================
echo  Setup complete!
echo.
echo  To test right now (no email sent):
echo    python main.py --test
echo.
echo  To send a real summary now:
echo    python main.py
echo.
echo  Logs will be written to:
echo    %LOG_DIR%\daily_summary.log
echo ============================================================
echo.
pause
