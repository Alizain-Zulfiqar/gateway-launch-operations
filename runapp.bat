@echo off
REM Gateway Launch Operations — Windows launcher (clone-and-run).
cd /d "%~dp0"

if not exist "%~dp0.matplotlib_cache" mkdir "%~dp0.matplotlib_cache"
set "MPLCONFIGDIR=%~dp0.matplotlib_cache"

if "%1"=="test" (
    if not exist venv\Scripts\python.exe goto :create_venv
    call venv\Scripts\activate.bat
    python -m pytest %2 %3 %4 %5
    goto :end
)

if not exist venv\Scripts\python.exe goto :create_venv
call venv\Scripts\activate.bat
python main.py %*
goto :end

:create_venv
echo First run: creating virtual environment (Python 3.11+ required)...
py -3.12 -m venv venv 2>nul || py -3.11 -m venv venv 2>nul || py -3 -m venv venv 2>nul || python -m venv venv
if errorlevel 1 (
    echo ERROR: Python 3.11+ not found. Install from https://www.python.org/downloads/
    pause
    exit /b 1
)
call venv\Scripts\activate.bat
python -m pip install -U pip
pip install -r requirements.txt
echo.
python main.py %*

:end
