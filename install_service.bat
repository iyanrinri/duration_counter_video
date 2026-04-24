@echo off
setlocal
cd /d "%~dp0"

set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\DurationCounter.lnk"
set "VBS_PATH=%cd%\run_hidden.vbs"

echo Mendaftarkan aplikasi ke Startup Folder...
echo Set oWS = WScript.CreateObject("WScript.Shell") > CreateShortcut.vbs
echo sLinkFile = "%SHORTCUT_PATH%" >> CreateShortcut.vbs
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> CreateShortcut.vbs
echo oLink.TargetPath = "wscript.exe" >> CreateShortcut.vbs
echo oLink.Arguments = """" ^& "%VBS_PATH%" ^& """" >> CreateShortcut.vbs
echo oLink.WorkingDirectory = "%cd%" >> CreateShortcut.vbs
echo oLink.Save >> CreateShortcut.vbs

cscript /nologo CreateShortcut.vbs
del CreateShortcut.vbs

if exist "%SHORTCUT_PATH%" (
    echo.
    echo ===================================================
    echo BERHASIL: Aplikasi telah didaftarkan ke Startup.
    echo Aplikasi akan berjalan otomatis di background 
    echo setiap kali Anda menyalakan laptop dan Log In.
    echo (Bebas dari masalah batasan baterai laptop)
    echo ===================================================
) else (
    echo.
    echo GAGAL: Terjadi kesalahan saat membuat shortcut startup.
)

pause
