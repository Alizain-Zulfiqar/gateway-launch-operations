@echo off
REM Build a standalone Windows folder: dist\GatewayLaunch\GatewayLaunch.exe
cd /d "%~dp0"

echo Refreshing bundled credentials and seed database...
python scripts\prepare_packaging_assets.py
if errorlevel 1 (
    echo prepare_packaging_assets.py failed.
    pause
    exit /b 1
)

if not exist venv\Scripts\python.exe (
    py -3 -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt -r requirements-build.txt
) else (
    call venv\Scripts\activate.bat
    pip install -r requirements-build.txt
)

pyinstaller --noconfirm gateway.spec
echo.
echo Build complete: dist\GatewayLaunch\
echo Zip that folder and share with Windows users (no Python install required).
pause
