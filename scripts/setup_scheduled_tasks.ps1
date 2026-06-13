#Requires -Version 5.1
<#
.SYNOPSIS
  注册 ZXTT 自动化报告 Windows 计划任务。

  交易日标准：周一至周五，除沪深北交易所公告休市日；周六日固定休市（含调休上班日）。
  2026 休市安排见 packages/core/exchange_holidays.py（证监办发〔2025〕130 号）。

  触发器：早/午/晚/全天监控 → 周一～周五 + bat 交易日门禁；交易日前夜资讯 → 每天 22:00 + eve-news 门禁。
  启动方式：wscript + run_hidden.vbs，无 cmd 黑窗（任务属性 Hidden）。
  时刻表：
    09:14  全天监控 intraday
    09:15  早盘 pre 采集
    09:25  早盘报告
    12:50  午间报告
    22:00  晚间报告（仅交易日）
    22:00  交易日前夜资讯更新（仅休市前夜：周日晚、长假最后一晚等）
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
        [TimeSpan]$ExecutionTimeLimit = (New-TimeSpan -Hours 3),
        [ValidateSet("Weekly", "Daily")]
        [string]$Schedule = "Weekly"
    )
    $bat = Join-Path $ProjectRoot $BatRelative
    if (-not (Test-Path $bat)) {
        throw "缺少脚本: $bat"
    }
    $vbs = Join-Path $ProjectRoot "scripts\run_hidden.vbs"
    if (-not (Test-Path $vbs)) {
        throw "缺少脚本: $vbs"
    }
    $taskName = "ZXTT-$Name"
    if ($Force -or (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue)) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    }
    # wscript //B + run_hidden.vbs：用户登录态下无 cmd 黑窗弹出（仍可在同会话开浏览器）
    $action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "//B `"$vbs`" `"$BatRelative`"" -WorkingDirectory $ProjectRoot
    if ($Schedule -eq "Daily") {
        $trigger = New-ScheduledTaskTrigger -Daily -At $At
    } else {
        $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $At
    }
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit $ExecutionTimeLimit -Hidden
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description $Description | Out-Null
    Write-Host "OK  $taskName  @ $At ($Schedule)  ->  $BatRelative"
}

Write-Host "项目目录: $ProjectRoot"
Write-Host ""

New-ZxttTask -Name "Intraday-Watch" -BatRelative "scripts\run_intraday_watch.bat" -At "09:14" -Description "ZXTT intraday watch 09:15-15:00 (auction + trading)" -ExecutionTimeLimit (New-TimeSpan -Hours 7)
New-ZxttTask -Name "Morning-Pre" -BatRelative "scripts\run_morning_pre.bat" -At "09:15" -Description "ZXTT morning pre collect"
New-ZxttTask -Name "Morning-Report" -BatRelative "scripts\run_morning_report.bat" -At "09:25" -Description "ZXTT morning report + wechat"
New-ZxttTask -Name "Midday" -BatRelative "scripts\run_midday.bat" -At "12:50" -Description "ZXTT midday report + wechat"
New-ZxttTask -Name "Evening" -BatRelative "scripts\run_evening.bat" -At "22:00" -Description "ZXTT evening report on trading days"
New-ZxttTask -Name "Eve-News" -BatRelative "scripts\run_eve_news.bat" -At "22:00" -Schedule Daily -Description "ZXTT eve news update before next trading day"

Write-Host ""
Write-Host "Done. Open Task Scheduler and filter ZXTT-"
