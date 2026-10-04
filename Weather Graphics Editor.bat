@echo off
title Weather Graphics Editor
REM Opens the Weather Graphics Editor in your browser (http://localhost:8770). Close this window to stop it.
cd /d "%~dp0"
call conda activate wxgfx 2>nul
python weather_graphics_editor.py
