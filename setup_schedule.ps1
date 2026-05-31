# Registers a Windows Scheduled Task that runs the Wyckoff scanner in email mode
# every day at 6:00 PM. Re-run this script to update the task.

$ErrorActionPreference = "Stop"

$taskName  = "WyckoffDailyAlerts"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$scanner   = Join-Path $scriptDir "scanner.py"

# Locate python.exe (prefer the launcher, fall back to PATH)
$python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $python) {
    $python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
}
if (-not (Test-Path $python)) {
    throw "Could not find python.exe. Edit `$python in this script to point at your install."
}

Write-Host "Python : $python"
Write-Host "Scanner: $scanner"

$action = New-ScheduledTaskAction `
    -Execute $python `
    -Argument "`"$scanner`" --email" `
    -WorkingDirectory $scriptDir

$trigger = New-ScheduledTaskTrigger -Daily -At 6:00PM

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

# Remove any existing task with the same name, then register fresh
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Wyckoff scanner daily email — setups scoring 80+ (bullish & bearish)" | Out-Null

Write-Host ""
Write-Host "Scheduled task '$taskName' registered: runs daily at 6:00 PM." -ForegroundColor Green
Write-Host "Test it now with:  Start-ScheduledTask -TaskName $taskName"
Write-Host "Remove it with:    Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false"
