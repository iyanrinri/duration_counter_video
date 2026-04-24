@echo off
set "TASK_NAME=DurationCounterService"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\DurationCounter.lnk"

echo Menghapus task dari Task Scheduler (jika ada)...
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

echo Menghapus shortcut dari Startup folder...
if exist "%SHORTCUT_PATH%" (
    del "%SHORTCUT_PATH%"
    echo Shortcut Startup berhasil dihapus.
) else (
    echo Shortcut Startup tidak ditemukan.
)

echo.
echo Service/Aplikasi berhasil dihapus dari Startup.
pause
