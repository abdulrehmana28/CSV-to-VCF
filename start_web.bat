@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1

rem Prefer the Windows Python launcher, then fall back to python.exe.
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
if not errorlevel 1 goto run_py

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
if not errorlevel 1 goto run_python

echo.
echo Python 3.8 or newer was not found on this computer.
echo.
echo Install it from https://www.python.org/downloads/
echo During installation, select "Add Python to PATH".
echo.
pause
exit /b 1

:run_py
py -3 webapp.py %*
goto end

:run_python
python webapp.py %*
goto end

:end
if errorlevel 1 (
    echo.
    echo The app stopped with an error. Read the message above.
    pause
)
endlocal
