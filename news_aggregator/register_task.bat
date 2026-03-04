@echo off
REM Register the HealthcareVCNewsBot Task Scheduler job
REM Runs every day (Mon-Sun) at 8:00 AM ET

set SCRIPT_DIR=%~dp0
set TASK_NAME=HealthcareVCNewsBot

REM Delete existing task if present
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

REM Create: daily, 8:00 AM, every day of the week
schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "\"%SCRIPT_DIR%run_news.bat\"" ^
    /sc DAILY ^
    /st 08:00 ^
    /ru "%USERNAME%" ^
    /rl LIMITED ^
    /f

if errorlevel 1 (
    echo ERROR: Could not register scheduled task.
    exit /b 1
)

echo.
echo [OK] Task "%TASK_NAME%" registered: runs every day at 8:00 AM.
schtasks /query /tn "%TASK_NAME%" /fo LIST
