#Requires -Version 5.1
<#
.SYNOPSIS
  注册 ZXTT 自动化报告 Windows 计划任务。

  交易日标准：周一至周五，除沪深北交易所公告休市日；周六日固定休市（含调休上班日）。
  2026 休市安排见 packages/core/exchange_holidays.py（证监办发〔2025〕130 号）。

  触发器：仅周一～周五；节假日与 bat 内 trading_day_gate 双重跳过。
  时刻表：
    09:14  全天监控 intraday（竞价 9:15-9:25 + 正式交易，单进程）
    09:15  早盘 pre 采集（并行）
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
        [string]$Description,
        [TimeSpan]$ExecutionTimeLimit = (New-TimeSpan -Hours 3)
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
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $At
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit $ExecutionTimeLimit
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description $Description | Out-Null
    Write-Host "OK  $taskName  @ $At  ->  $BatRelative"
}

Write-Host "项目目录: $ProjectRoot"
Write-Host ""

New-ZxttTask -Name "Intraday-Watch" -BatRelative "scripts\run_intraday_watch.bat" -At "09:14" -Description "ZXTT intraday watch 09:15-15:00 (auction + trading)" -ExecutionTimeLimit (New-TimeSpan -Hours 7)
New-ZxttTask -Name "Morning-Pre" -BatRelative "scripts\run_morning_pre.bat" -At "09:15" -Description "ZXTT morning pre collect"
New-ZxttTask -Name "Morning-Report" -BatRelative "scripts\run_morning_report.bat" -At "09:25" -Description "ZXTT morning report + wechat"
New-ZxttTask -Name "Midday" -BatRelative "scripts\run_midday.bat" -At "12:50" -Description "ZXTT midday report + wechat"
New-ZxttTask -Name "Evening" -BatRelative "scripts\run_evening.bat" -At "22:00" -Description "ZXTT evening report + wechat"

Write-Host ""
Write-Host "Done. Open Task Scheduler and filter ZXTT-"
