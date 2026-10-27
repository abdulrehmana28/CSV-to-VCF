@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1

rem Prefer the Windows Python launcher, then fall back to python.exe.
py -3 --version >nul 2>nul
if not errorlevel 1 goto run_py

python -c "import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)" >nul 2>nul
if not errorlevel 1 goto run_python

echo.
echo Python 3 was not found on this computer.
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
