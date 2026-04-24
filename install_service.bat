@echo off
setlocal
cd /d "%~dp0"

set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\DurationCounter.lnk"
set "VBS_PATH=%cd%\run_hidden.vbs"
set "WORKING_DIR=%cd%"

echo Mendaftarkan aplikasi ke Startup Folder...

powershell -ExecutionPolicy Bypass -Command ^
    "$ws = New-Object -ComObject WScript.Shell; " ^
    "$s = $ws.CreateShortcut('%SHORTCUT_PATH%'); " ^
    "$s.TargetPath = 'wscript.exe'; " ^
    "$s.Arguments = '\"%VBS_PATH%\"'; " ^
    "$s.WorkingDirectory = '%WORKING_DIR%'; " ^
    "$s.Save()"

if exist "%SHORTCUT_PATH%" (
    echo.
    echo ===================================================
    echo BERHASIL: Aplikasi telah didaftarkan ke Startup.
    echo Aplikasi akan berjalan otomatis di background 
    echo setiap kali Anda menyalakan laptop dan Log In.
    echo (Bebas dari masalah batasan baterai laptop^)
    echo ===================================================
) else (
    echo.
    echo GAGAL: Terjadi kesalahan saat membuat shortcut startup.
    echo Pastikan Anda memiliki izin untuk menulis ke folder Startup.
)

pause
