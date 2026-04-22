@echo off
chcp 65001 >nul

REM Activate venv dan jalankan script
if not exist venv (
    echo Virtual environment not found. Run setup_venv.bat first!
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python monitor_drives.py
pause
