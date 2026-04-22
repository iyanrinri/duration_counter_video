@echo off
setlocal
cd /d "%~dp0"

set TASK_NAME=DurationCounterService
set VBS_PATH=%cd%\run_hidden.vbs

echo Menghapus task lama jika ada...
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

echo Mendaftarkan task baru ke Task Scheduler...
echo Task ini akan berjalan otomatis setiap kali Anda Log In.
schtasks /create /tn "%TASK_NAME%" /tr "wscript.exe \"%VBS_PATH%\"" /sc onlogon /rl highest

if %errorlevel% equ 0 (
    echo.
    echo ===================================================
    echo BERHASIL: Service telah didaftarkan.
    echo Script akan berjalan otomatis di background 
    echo setiap kali Anda menyalakan laptop dan Log In.
    echo ===================================================
) else (
    echo.
    echo GAGAL: Terjadi kesalahan saat mendaftarkan service.
    echo Pastikan Anda menjalankan script ini sebagai Administrator.
)

pause
