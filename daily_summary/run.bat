@echo off
REM ============================================================
REM  run.bat — called by Windows Task Scheduler at 5:30 PM ET
REM  to generate and email the daily summary.
REM ============================================================

REM Change to the directory that contains this script
cd /d "%~dp0"

REM Activate the virtual environment (created by setup_scheduler.bat)
call "%~dp0venv\Scripts\activate.bat"

REM Run the daily summary bot
python main.py >> "%~dp0logs\daily_summary.log" 2>&1

REM Deactivate venv (optional, but clean)
call deactivate
