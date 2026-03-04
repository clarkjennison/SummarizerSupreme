@echo off
REM ============================================================
REM  run_news.bat — called by Windows Task Scheduler at 8 AM ET
REM ============================================================
cd /d "%~dp0"
call "%~dp0venv\Scripts\activate.bat"
python main.py >> "%~dp0logs\news_aggregator.log" 2>&1
call deactivate
