@echo off
setlocal
cd /d "%~dp0"
python research_digest.py
if errorlevel 1 (
    echo.
    echo Reading recommendation failed.
    pause
    exit /b 1
)
echo.
echo Reading recommendation completed.
pause
endlocal
