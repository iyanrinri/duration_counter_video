@echo off
set TASK_NAME=DurationCounterService

echo Menghapus task %TASK_NAME%...
schtasks /delete /tn "%TASK_NAME%" /f

if %errorlevel% equ 0 (
    echo Service berhasil dihapus.
) else (
    echo Service tidak ditemukan atau gagal dihapus.
)

pause
