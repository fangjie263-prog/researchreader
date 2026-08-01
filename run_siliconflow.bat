@echo off
title SiliconFlow API Status
cd /d "%~dp0"
python siliconflow_status.py %*
echo.
pause
