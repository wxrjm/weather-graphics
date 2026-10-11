@echo off
REM One-time setup: adds a Windows scheduled task that runs cleanup_output.bat every hour.
REM Double-click this file once. To remove the task later:  schtasks /Delete /TN "Weather Graphics Cleanup" /F
schtasks /Create /F /SC HOURLY /TN "Weather Graphics Cleanup" /TR "\"%~dp0cleanup_output.bat\""
if %errorlevel%==0 (echo. & echo Scheduled: "Weather Graphics Cleanup" runs every hour.) else (echo. & echo Could not create the task - try right-clicking this file and choosing Run as administrator.)
pause
