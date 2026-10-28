param(
    [string]$Python = '.venv/Scripts/python.exe',
    [ValidateRange(1024, 65535)][int]$Port = 8000,
    [switch]$Restart
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
if (-not [IO.Path]::IsPathRooted($Python)) { $Python = Join-Path $projectRoot $Python }
$runtimePython = (Resolve-Path -LiteralPath $Python).Path
& $runtimePython -c "import sys, django; assert sys.version_info[:2] == (3, 13); assert django.VERSION[:2] == (5, 2)"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 / Django 5.2 runtime required.' }
$recordRoot = Join-Path $projectRoot '.scratch/runtime'
$metadataPath = Join-Path $recordRoot "preview-$Port.json"
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    if (-not $Restart -or -not (Test-Path -LiteralPath $metadataPath)) { throw 'Port is in use; no process was stopped.' }
    $previous = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    $expectedCommand = 'manage\.py runserver 127\.0\.0\.1:' + $Port + ' --noreload'
    if ($previous.pid -ne $process.ProcessId -or $previous.root -ne $projectRoot -or
        $process.ExecutablePath -ne $previous.python -or $process.CommandLine -notmatch $expectedCommand) {
        throw 'Preview identity changed; no process was stopped.'
    }
    Stop-Process -Id $process.ProcessId
}
New-Item -ItemType Directory -Path $recordRoot -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$stdout = Join-Path $recordRoot "preview-$Port-$stamp.out.log"
$stderr = Join-Path $recordRoot "preview-$Port-$stamp.err.log"
$started = Start-Process -FilePath $runtimePython -ArgumentList @('-X','utf8','-u','manage.py','runserver',"127.0.0.1:$Port",'--noreload') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$deadline = (Get-Date).AddSeconds(30)
$ownedProcess = $null
while ((Get-Date) -lt $deadline) {
    $activeListener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($activeListener) {
        $candidate = Get-CimInstance Win32_Process -Filter "ProcessId=$($activeListener.OwningProcess)"
        # Windows venv's redirector can own a separate interpreter child.
        if ($candidate.ProcessId -ne $started.Id -and $candidate.ParentProcessId -ne $started.Id) {
            throw 'Port owner is unrelated to the launched interpreter.'
        }
        if ($candidate.CommandLine -notmatch ('manage\.py runserver 127\.0\.0\.1:' + $Port + ' --noreload')) {
            throw 'Unexpected listener command; no process was stopped.'
        }
        $ownedProcess = $candidate
        break
    }
    if ($started.HasExited) { throw "Preview exited; inspect $stderr" }
    Start-Sleep -Milliseconds 250
}
if (-not $ownedProcess) { throw "Preview readiness timed out; inspect $stderr" }
[ordered]@{pid=$ownedProcess.ProcessId; launcher_pid=$started.Id; root=$projectRoot; python=$ownedProcess.ExecutablePath; runtime=$runtimePython; port=$Port; stdout=$stdout; stderr=$stderr} |
    ConvertTo-Json | Set-Content -LiteralPath $metadataPath -Encoding utf8
Write-Output "Preview process $($ownedProcess.ProcessId): http://127.0.0.1:$Port/login.html"
