#Requires -Version 5.1
<#
.SYNOPSIS
  注册 ZXTT 自动化报告 Windows 计划任务。

  时刻表（非交易日由程序内日历自动跳过）：
    09:15  集合竞价采集 + 早盘 pre 采集（并行）
    09:25  早盘集合竞价报告
    12:50  午间报告
    22:00  晚间盘后报告
#>
param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function New-ZxttTask {
    param(
        [string]$Name,
        [string]$BatRelative,
        [string]$At,
        [string]$Description
    )
    $bat = Join-Path $ProjectRoot $BatRelative
    if (-not (Test-Path $bat)) {
        throw "缺少脚本: $bat"
    }
    $taskName = "ZXTT-$Name"
    if ($Force -or (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue)) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    }
    $action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$bat`"" -WorkingDirectory $ProjectRoot
    $trigger = New-ScheduledTaskTrigger -Daily -At $At
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description $Description | Out-Null
    Write-Host "OK  $taskName  @ $At  ->  $BatRelative"
}

Write-Host "项目目录: $ProjectRoot"
Write-Host ""

New-ZxttTask -Name "Auction-Watch" -BatRelative "scripts\run_auction_watch.bat" -At "09:15" -Description "ZXTT auction watch 09:15-09:25"
New-ZxttTask -Name "Morning-Pre" -BatRelative "scripts\run_morning_pre.bat" -At "09:15" -Description "ZXTT morning pre collect"
New-ZxttTask -Name "Morning-Report" -BatRelative "scripts\run_morning_report.bat" -At "09:25" -Description "ZXTT morning report + wechat"
New-ZxttTask -Name "Midday" -BatRelative "scripts\run_midday.bat" -At "12:50" -Description "ZXTT midday report + wechat"
New-ZxttTask -Name "Evening" -BatRelative "scripts\run_evening.bat" -At "22:00" -Description "ZXTT evening report + wechat"

Write-Host ""
Write-Host "Done. Open Task Scheduler and filter ZXTT-"
