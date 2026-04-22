@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo Creating Virtual Environment (venv)
echo ========================================

REM Hapus venv lama jika ada
if exist venv (
    echo Removing old venv...
    rmdir /s /q venv
)

REM Buat venv baru
echo Creating new virtual environment...
python -m venv venv

REM Activate venv
echo Activating venv...
call venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install requirements
echo Installing requirements...
pip install -r requirements.txt

echo.
echo ========================================
echo ✓ Setup complete!
echo ========================================
echo.
echo To activate venv in future, run:
echo   venv\Scripts\activate.bat
echo.
echo To run the script:
echo   python monitor_drives.py
echo.
echo To deactivate venv:
echo   deactivate
echo.
pause
