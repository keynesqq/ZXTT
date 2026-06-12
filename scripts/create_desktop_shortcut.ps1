#Requires -Version 5.1
param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$ShortcutName = ("ZXTT " + [char]0x4F5C + [char]0x6218 + [char]0x5361)
)

$bat = Join-Path $ProjectRoot "scripts\open_hub.bat"
if (-not (Test-Path $bat)) {
    throw "Missing: $bat"
}

$desktop = [Environment]::GetFolderPath("Desktop")
$lnk = Join-Path $desktop ($ShortcutName + ".lnk")

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnk)
$sc.TargetPath = $bat
$sc.WorkingDirectory = $ProjectRoot
$sc.Description = "ZXTT report hub"
$sc.Save()

Write-Host "OK  $lnk"
