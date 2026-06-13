' 计划任务无窗口启动：wscript.exe //B scripts\run_hidden.vbs scripts\run_xxx.bat
Option Explicit

If WScript.Arguments.Count < 1 Then
    WScript.Quit 1
End If

Dim fso, sh, scriptDir, projectRoot, batRel, batPath
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
projectRoot = fso.GetParentFolderName(scriptDir)
batRel = WScript.Arguments(0)
batPath = fso.BuildPath(projectRoot, batRel)

If Not fso.FileExists(batPath) Then
    WScript.Quit 1
End If

sh.CurrentDirectory = projectRoot
' 0 = hidden window; wait=False 与计划任务「独立进程」一致
sh.Run "cmd /c """ & batPath & """", 0, False
