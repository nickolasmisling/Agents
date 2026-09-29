<#
.SYNOPSIS
    Removes old batchtrack log folders and temporary export files.

.DESCRIPTION
    Intended to run nightly from Task Scheduler on the batchtrack application
    server. Deletes dated log folders older than the retention period, removes
    matching temporary export files from the file share, then prints a summary
    of what is left.

.PARAMETER RetentionDays
    Number of days of logs to keep. Defaults to 30.

.PARAMETER Pattern
    File name pattern for temporary export files. Defaults to *.tmp.csv.

.EXAMPLE
    .\Cleanup-Logs.ps1 -RetentionDays 14
#>
param(
    [ValidateRange(1, 3650)]
    [int]$RetentionDays = 30,

    [string]$Pattern = "*.tmp.csv"
)

$LogRoot = "D:\batchtrack\logs"
$ExportRoot = "\\bog-fs01\batchtrack\exports\tmp"
$cutoff = (Get-Date).AddDays(-$RetentionDays)

Write-Host "Removing batchtrack logs last written before $($cutoff.ToString('yyyy-MM-dd'))"

$oldFolders = Get-ChildItem -Path $LogRoot -Directory |
    Where-Object { $_.LastWriteTime -lt $cutoff }

foreach ($folder in $oldFolders) {
    Write-Host "  deleting $($folder.FullName)"
    Remove-Item -Path $folder.FullName -Recurse -Force
}

Write-Host "Removing temporary exports matching $Pattern"
$cleanup = "Get-ChildItem -Path '$ExportRoot' -Filter $Pattern -File -Recurse | " +
    "Where-Object { `$_.LastWriteTime -lt `$cutoff } | Remove-Item -Force"
Invoke-Expression $cleanup

$remaining = Get-ChildItem -Path $LogRoot -Recurse -File
$totalMb = [math]::Round((($remaining | Measure-Object -Property Length -Sum).Sum) / 1MB, 2)

Write-Host ""
Write-Host "Name`tSizeBytes`tLastWriteTime"
foreach ($file in $remaining) {
    Write-Host "$($file.Name)`t$($file.Length)`t$($file.LastWriteTime.ToString('s'))"
}
Write-Host "$($remaining.Count) log files remaining, $totalMb MB"
