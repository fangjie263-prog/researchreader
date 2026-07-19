@echo off
title ResearchReader - HKEJ

:MENU
cls
echo ============================================
echo          ResearchReader - HKEJ
echo ============================================
echo.
echo 1. Fetch 1 page
echo 2. Fetch 2 pages
echo 3. Fetch 5 pages
echo 4. Fetch 10 pages
echo 5. Custom pages
echo.
echo 0. Exit
echo.
set /p choice=Select: 

if "%choice%"=="1" set pages=1
if "%choice%"=="2" set pages=2
if "%choice%"=="3" set pages=5
if "%choice%"=="4" set pages=10

if "%choice%"=="5" (
    set /p pages=Enter number of pages:
)

if "%choice%"=="0" exit

if not defined pages goto MENU

echo.
echo ============================================
echo Fetching %pages% page(s)...
echo ============================================
echo.

python work\hkej_scraper.py -n %pages%

echo.
echo ============================================
echo Converting latest news to HTML...
echo ============================================
python hkej_to_html.py --latest

echo.
echo ============================================
echo Finished!
echo Output folder:
echo.
echo work\outputs\ and output\
echo ============================================
echo.

explorer output

echo.
pause
