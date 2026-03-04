@echo off
schtasks /delete /tn "DailySummaryBot" /f >nul 2>&1
schtasks /create /tn "DailySummaryBot" /tr "\"C:\Users\Clark Jennison\Budget Bot\.claude\worktrees\goofy-easley\daily_summary\run.bat\"" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 17:30 /ru "%USERNAME%" /rl LIMITED /f
echo Exit code: %ERRORLEVEL%
