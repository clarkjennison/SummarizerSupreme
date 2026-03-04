@echo off
REM ============================================================
REM  run_weekly.bat — called by Windows Task Scheduler at 5:31 PM
REM  every Friday to generate and email the weekly wrap-up.
REM ============================================================

REM Change to the directory that contains this script
cd /d "%~dp0"

REM Activate the virtual environment
call "%~dp0venv\Scripts\activate.bat"

REM Run the weekly summary bot
python main.py --weekly >> "%~dp0logs\weekly_summary.log" 2>&1

REM Deactivate venv
call deactivate
