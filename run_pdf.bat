@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import pdfplumber" >nul 2>&1
    if not errorlevel 1 set "PYTHON_EXE=.venv\Scripts\python.exe"
)

echo Using Python: %PYTHON_EXE%
"%PYTHON_EXE%" pdf_queue.py
if errorlevel 1 (
    echo.
    echo PDF queue failed. Check the error above.
    pause
    exit /b 1
)

echo.
echo PDF queue completed.
pause
endlocal
