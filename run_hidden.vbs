Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strPath

' Run run.bat (monitor) hidden
WshShell.Run "cmd.exe /c run.bat", 0, False
' Run run_app.bat (web app) hidden
WshShell.Run "cmd.exe /c run_app.bat", 0, False
