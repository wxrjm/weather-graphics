@echo off
REM Double-click or point Windows Task Scheduler at this file.
REM Edit the conda env name below if yours differs.
cd /d "%~dp0"
call conda activate wxgfx 2>nul
python run.py %*
