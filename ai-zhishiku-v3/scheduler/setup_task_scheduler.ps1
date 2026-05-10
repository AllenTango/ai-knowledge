<#
.SYNOPSIS
    Windows Task Scheduler setup script for knowledge collection.

.DESCRIPTION
    Creates a daily scheduled task named "AIMC-KnowledgeCollect"
    to run at 16:00 (Beijing time).

.NOTES
    Requires Administrator privileges.
    Default sources: github,rss, limit: 20.

.EXAMPLE
    .\setup_task_scheduler.ps1
    .\setup_task_scheduler.ps1 -Sources github -Limit 10
    .\setup_task_scheduler.ps1 -DryRun
#>

param(
    [string]$TaskName = "AIMC-KnowledgeCollect",
    [string]$Sources = "github,rss",
    [int]$Limit = 20,
    [switch]$DryRun
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Resolve-Path "$ScriptDir\.."
$PsScript = Join-Path $ScriptDir "run_pipeline.ps1"

$ActionArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$PsScript`" -Sources $Sources -Limit $Limit"
$ScheduleTime = "16:00"

if ($DryRun) {
    Write-Host "========== Dry Run: Configuration Info =========="
    Write-Host "Task Name : $TaskName"
    Write-Host "Project   : $ProjectDir"
    Write-Host "Script    : $PsScript"
    Write-Host "Schedule  : Daily at $ScheduleTime (UTC+8)"
    Write-Host "Args      : --sources $Sources --limit $Limit"
    Write-Host "Log Dir   : $ProjectDir\logs"
    Write-Host ""
    Write-Host "To create the task for real, run this script without -DryRun"
    Write-Host "as Administrator."
    exit 0
}

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if (-not $isAdmin) {
    Write-Error "This script requires Administrator privileges. Please run PowerShell as Administrator."
    exit 1
}

$TaskCommand = "powershell.exe"
$TaskArgs = $ActionArgs

try {
    schtasks /Create /SC DAILY /TN $TaskName /TR "$TaskCommand $TaskArgs" /ST $ScheduleTime /F /RL HIGHEST
    Write-Host "Task '$TaskName' created successfully."
    Write-Host "Schedule: Daily at $ScheduleTime (UTC+8)"
    Write-Host "Log Dir : $ProjectDir\logs"
}
catch {
    Write-Error "Failed to create task: $_"
    exit 1
}
