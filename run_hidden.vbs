Set WshShell = CreateObject("WScript.Shell")
' Lay duong dan thu muc hien tai
Set FSO = CreateObject("Scripting.FileSystemObject")
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)

' Chay run.bat o che do an cua so (0 = Hide, False = khong block)
WshShell.CurrentDirectory = ScriptDir
WshShell.Run "cmd /c run.bat", 0, False
