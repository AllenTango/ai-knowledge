# 知识库自动化采集 - Windows 本地定时任务脚本
# 运行 pipeline/pipeline.py，记录日志，自动清理过期日志

param(
    [string]$Sources = "github,rss",
    [int]$Limit = 20,
    [int]$RetentionDays = 30
)

$ErrorActionPreference = "Continue"

# 强制 UTF-8 编码，防止控制台乱码
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Resolve-Path "$ScriptDir\.."
$LogDir = Join-Path $ProjectDir "logs"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd_HHmmss")
$LogFile = Join-Path $LogDir "collect_$Timestamp.log"
$HistoryLog = Join-Path $LogDir "collect_history.log"

$Utf8NoBom = New-Object System.Text.UTF8Encoding $false

function Write-Log {
    param([string]$Message)
    $Line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    # Write raw UTF-8 bytes to file, bypassing any encoding conversion
    $utf8Bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($Line + "`r`n")
    [System.IO.File]::AppendAllBytes($LogFile, $utf8Bytes)
    Write-Host $Line
}

function Clear-OldLogs {
    param([int]$Days)
    Write-Log "清理 $Days 天前的日志..."
    $Cutoff = (Get-Date).AddDays(-$Days)
    Get-ChildItem -LiteralPath $LogDir -Filter "collect_*.log" |
        Where-Object { $_.LastWriteTime -lt $Cutoff } |
        Remove-Item -Force
}

function Invoke-Pipeline {
    Write-Log "========== 知识库采集开始 =========="
    Write-Log "参数: sources=$Sources, limit=$Limit"

    $Stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $ExitCode = 0
    $TempOutputFile = Join-Path $LogDir "temp_output.bin"

    try {
        Push-Location -LiteralPath $ProjectDir
        $env:PYTHONIOENCODING = "utf-8"
        $env:PYTHONUTF8 = "1"
        # Use cmd /c to capture raw UTF-8 bytes directly, avoiding PowerShell pipe encoding conversion
        cmd /c "python -X utf8 -u pipeline\pipeline.py --sources $Sources --limit $Limit --verbose > `"$TempOutputFile`" 2>&1 & exit %errorlevel%" | Out-Null
        $ExitCode = $LASTEXITCODE
        Pop-Location
    }
    catch {
        $ExitCode = 1
        Pop-Location
    }

    if (Test-Path $TempOutputFile) {
        $fs = [System.IO.File]::OpenRead($TempOutputFile)
        $sw = New-Object System.IO.StreamWriter($LogFile, $true, $Utf8NoBom)
        $buffer = New-Object byte[] 8192
        $bytesRead = 0
        do {
            $bytesRead = $fs.Read($buffer, 0, $buffer.Length)
            if ($bytesRead -gt 0) {
                $sw.BaseStream.Write($buffer, 0, $bytesRead)
            }
        } while ($bytesRead -eq $buffer.Length)
        $sw.Flush()
        $sw.Close()
        $fs.Close()
        Remove-Item $TempOutputFile -Force
    }

    $Stopwatch.Stop()
    $Duration = [math]::Round($Stopwatch.Elapsed.TotalSeconds, 0)

    if ($ExitCode -eq 0) {
        Write-Log "采集成功，耗时 ${Duration}s"
    } else {
        Write-Log "采集失败，退出码: $ExitCode，耗时 ${Duration}s"
    }

    Write-Log "========== 采集结束 =========="
    return @{ ExitCode = $ExitCode; Duration = $Duration }
}

$Result = Invoke-Pipeline

$LogContent = [System.IO.File]::ReadAllBytes($LogFile)
$Lines = [System.Text.Encoding]::UTF8.GetString($LogContent).Split("`r`n")
$Sw = New-Object System.IO.StreamWriter($HistoryLog, $true, $Utf8NoBom)
foreach ($Line in $Lines) {
    $Sw.WriteLine($Line)
}
$Sw.WriteLine("")
$Sw.Close()

Clear-OldLogs -Days $RetentionDays

if ($Result.ExitCode -ne 0) {
    throw "采集失败，退出码: $($Result.ExitCode)"
}