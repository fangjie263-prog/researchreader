@echo off
cd /d "%~dp0"
python core_pipeline.py %*
pause
