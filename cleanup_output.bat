@echo off
REM Deletes graphics run folders older than 48 hours (config.json "keep_hours"). Safe to run any time.
cd /d "%~dp0"
python cleanup_output.py >> "%~dp0cleanup_log.txt" 2>&1
