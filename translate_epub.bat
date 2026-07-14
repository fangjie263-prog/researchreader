@echo off
setlocal EnableDelayedExpansion

cd /d "%~dp0"

set "BOOKDIR=D:\AIProjects\ResearchReader\books"
set "COUNT=0"

for %%F in ("%BOOKDIR%\*.epub") do (
    set /a COUNT+=1
    set "BOOK=%%~fF"
    set "NAME=%%~nF"
)

if !COUNT! EQU 0 (
    echo.
    echo ERROR: No EPUB file found.
    echo Folder:
    echo %BOOKDIR%
    pause
    exit /b
)

if !COUNT! GTR 1 (
    echo.
    echo ERROR: More than one EPUB file found.
    echo Please keep only ONE EPUB in:
    echo %BOOKDIR%
    pause
    exit /b
)

echo.
echo ==========================================
echo EPUB:
echo !BOOK!
echo ==========================================
echo.

py -3.13 scripts\translate_epub.py "!BOOK!"

if errorlevel 1 (
    echo.
    echo Translation failed.
    pause
    exit /b
)

if not exist output mkdir output

copy /Y "temp\translated.epub" "output\!NAME!_zh.epub" >nul

echo.
echo ==========================================
echo Translation completed!
echo.
echo Output:
echo output\!NAME!_zh.epub
echo ==========================================

explorer output

pause