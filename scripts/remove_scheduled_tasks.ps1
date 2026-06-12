#Requires -Version 5.1
$names = @(
    "ZXTT-Intraday-Watch",
    "ZXTT-Auction-Watch",
    "ZXTT-Morning-Pre",
    "ZXTT-Morning-Report",
    "ZXTT-Midday",
    "ZXTT-Evening"
)
foreach ($n in $names) {
    Unregister-ScheduledTask -TaskName $n -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "移除: $n"
}
Write-Host "完成。"
