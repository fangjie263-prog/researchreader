@echo off
cd /d "%~dp0"

git pull

py -3.13 -m pip install -e .

pause