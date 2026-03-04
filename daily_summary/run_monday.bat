@echo off
REM ============================================================
REM  run_monday.bat — called by Windows Task Scheduler at 8:00 AM
REM  every Monday to generate and email the week-ahead briefing.
REM ============================================================

REM Change to the directory that contains this script
cd /d "%~dp0"

REM Activate the virtual environment
call "%~dp0venv\Scripts\activate.bat"

REM Run the Monday briefing bot
python main.py --monday >> "%~dp0logs\monday_briefing.log" 2>&1

REM Deactivate venv
call deactivate
