param(
    [string]$Python = '.venv/Scripts/python.exe',
    [string]$EnvFile = '.env',
    [string]$PostgresEnvFile = '.env.postgres',
    [string]$MediaRoot = 'media',
    [ValidateRange(1024,65535)][int]$Port = 8000,
    [ValidateRange(1024,65535)][int]$McpPort = 18082,
    [switch]$Restart
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Net.Http
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
function ProjectPath([string]$value) {
    if ([IO.Path]::IsPathRooted($value)) { return [IO.Path]::GetFullPath($value) }
    return [IO.Path]::GetFullPath((Join-Path $projectRoot $value))
}
function Get-ProfileWorkerTree([object[]]$Processes, [string]$ExpectedEntry) {
    $candidatePattern = '(?i)(?:^|\s)--profile-worker(?=\s|$)|(?:^|\s)"?profile_worker"?(?=\s|$)|profile-auto[^"\r\n]*[/\\]run_worker\.py(?=["\s]|$)'
    $candidates = @($Processes | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -match $candidatePattern })
    if (!$candidates.Count) { return }
    $entryPattern = '(?i)(?:^|\s)"?' + [regex]::Escape([IO.Path]::GetFullPath($ExpectedEntry).Replace('/','\')) + '"?(?=\s|$)'
    foreach ($candidate in $candidates) {
        $line = $candidate.CommandLine.Replace('/','\')
        if ($line -notmatch $entryPattern -or $line -notmatch '(?:^|\s)--profile-worker(?=\s|$)') {
            throw 'A profile worker has an unrecognized source; no profile process was stopped.'
        }
    }
    $ids = @($candidates | ForEach-Object ProcessId)
    $roots = @($candidates | Where-Object { $_.ParentProcessId -notin $ids })
    if ($roots.Count -ne 1) { throw 'Multiple profile worker launchers found; no profile process was stopped.' }
    $owned = [Collections.Generic.HashSet[int]]::new()
    [void]$owned.Add([int]$roots[0].ProcessId)
    do {
        $before = $owned.Count
        foreach ($process in $Processes) {
            if ($owned.Contains([int]$process.ParentProcessId)) { [void]$owned.Add([int]$process.ProcessId) }
        }
    } while ($owned.Count -ne $before)
    return @($Processes | Where-Object { $owned.Contains([int]$_.ProcessId) })
}
function Stop-VerifiedProfileTree([object[]]$Tree) {
    # Recheck each snapshot immediately before stopping, including PID reuse.
    $remaining = @($Tree)
    while ($remaining.Count) {
        $parents = @($remaining | ForEach-Object ParentProcessId)
        $leaves = @($remaining | Where-Object { $_.ProcessId -notin $parents })
        if (!$leaves.Count) { throw 'Invalid profile process ancestry; no additional process was stopped.' }
        foreach ($process in $leaves) {
            $live = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ProcessId)"
            if ($live) {
                if ($live.CreationDate -ne $process.CreationDate -or $live.CommandLine -ne $process.CommandLine -or
                    $live.ParentProcessId -ne $process.ParentProcessId) { throw 'Profile process identity changed; refusing stop.' }
                Stop-Process -Id $process.ProcessId -ErrorAction Stop
            }
        }
        $leafIds = @($leaves | ForEach-Object ProcessId)
        $remaining = @($remaining | Where-Object { $_.ProcessId -notin $leafIds })
    }
}
function Sync-ProfileWorkerCore([bool]$Enabled, [bool]$Restart, [string]$ProjectRoot,
                            [string]$Python, [string]$Entry, [object[]]$BaseArgs, [string]$RecordRoot) {
    $path = Join-Path $RecordRoot 'profile-worker.json'
    if (Test-Path -LiteralPath $path) {
        $previousProfile = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
        if ([IO.Path]::GetFullPath($previousProfile.root) -ne $ProjectRoot) { throw 'Profile registration belongs to another workspace.' }
    }
    $processes = @(Get-CimInstance Win32_Process)
    $tree = @(Get-ProfileWorkerTree $processes $Entry)
    if ($tree.Count) {
        if (!$Restart) { throw 'A profile worker already exists; use -Restart to load the current configuration.' }
        Stop-VerifiedProfileTree $tree
    }
    if (@(Get-ProfileWorkerTree @(Get-CimInstance Win32_Process) $Entry).Count) { throw 'A profile worker remains; no second worker was launched.' }
    $profileRecord = [ordered]@{root=$ProjectRoot;runtime=$Python;entry=$Entry;enabled=$Enabled;status='disabled';launcher_pid=$null}
    if (!$Enabled) {
        $profileRecord | ConvertTo-Json | Set-Content -LiteralPath $path -Encoding utf8
        return $profileRecord
    }
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff')
    $stdout = Join-Path $RecordRoot "profile-worker-$stamp.out.log"
    $stderr = Join-Path $RecordRoot "profile-worker-$stamp.err.log"
    $startedProfile = Start-Process -FilePath $Python -ArgumentList ($BaseArgs + @('--profile-worker')) -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $profileRecord.launcher_pid = $startedProfile.Id
    $profileRecord.status = 'starting'
    $profileRecord.stdout = $stdout
    $profileRecord.stderr = $stderr
    $profileRecord | ConvertTo-Json | Set-Content -LiteralPath $path -Encoding utf8
    try {
        $deadline = [DateTime]::UtcNow.AddSeconds(30)
        do {
            $startedProfile.Refresh()
            if ($startedProfile.HasExited) { throw 'Profile worker exited before readiness.' }
            if ((Test-Path -LiteralPath $stdout) -and
                (Select-String -LiteralPath $stdout -Pattern '^TEA_SAAS_PROFILE_WORKER_READY$' -Quiet)) {
                Start-Sleep -Milliseconds 500
                $live = Get-CimInstance Win32_Process -Filter "ProcessId=$($startedProfile.Id)"
                if ($live -and @(Get-ProfileWorkerTree @(Get-CimInstance Win32_Process) $Entry).Count) {
                    $startedProfile.Refresh()
                    if (!$startedProfile.HasExited) {
                        $profileRecord.creation_date = $live.CreationDate.ToUniversalTime().ToString('o')
                        $profileRecord.status = 'ready'
                        $profileRecord | ConvertTo-Json | Set-Content -LiteralPath $path -Encoding utf8
                        return $profileRecord
                    }
                }
            }
            Start-Sleep -Milliseconds 200
        } while ([DateTime]::UtcNow -lt $deadline)
        throw 'Profile worker readiness timed out.'
    } catch {
        # Cleanup only a tree rooted in the process this invocation just created.
        $cleanupConfirmed = $true
        try {
            $tree = @(Get-ProfileWorkerTree @(Get-CimInstance Win32_Process) $Entry)
            if (@($tree | Where-Object ProcessId -eq $startedProfile.Id).Count) { Stop-VerifiedProfileTree $tree }
            elseif ($tree.Count) { $cleanupConfirmed = $false }
        } catch { $cleanupConfirmed = $false }
        $profileRecord.status = 'failed'
        $profileRecord.cleanup_confirmed = $cleanupConfirmed
        $profileRecord | ConvertTo-Json | Set-Content -LiteralPath $path -Encoding utf8
        throw "Profile worker did not become ready; inspect $stderr"
    }
}
function Sync-ProfileWorker([bool]$Enabled, [bool]$Restart, [string]$ProjectRoot,
                            [string]$Python, [string]$Entry, [object[]]$BaseArgs, [string]$RecordRoot) {
    # Serialize two preview invocations without a stale PID or lock-file cleanup.
    $guard = [IO.File]::Open((Join-Path $RecordRoot 'profile-worker.lock'), [IO.FileMode]::OpenOrCreate,
                            [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try { return Sync-ProfileWorkerCore @PSBoundParameters }
    finally { $guard.Dispose() }
}
$runtimePython = (Resolve-Path -LiteralPath (ProjectPath $Python)).Path
$entry = Join-Path $PSScriptRoot 'backend.py'
$baseArgs = @('-X','utf8','-u',('"'+$entry+'"'),'--env-file',('"'+(ProjectPath $EnvFile)+'"'),
    '--postgres-env-file',('"'+(ProjectPath $PostgresEnvFile)+'"'),'--media-root',('"'+(ProjectPath $MediaRoot)+'"'),
    '--addrport',"127.0.0.1:$Port",'--mcp-port',"$McpPort")
$profileStateText = & $runtimePython -X utf8 -u $entry --env-file (ProjectPath $EnvFile) --postgres-env-file (ProjectPath $PostgresEnvFile) --media-root (ProjectPath $MediaRoot) --profile-status
if ($LASTEXITCODE -ne 0) { throw 'Cannot read profile runtime status; no service was stopped.' }
$profileState = $profileStateText | ConvertFrom-Json
if ($profileState.enabled -isnot [bool]) { throw 'Invalid profile runtime status; no service was stopped.' }
# Detect conflicting/foreign profile trees before changing the existing services.
$null = @(Get-ProfileWorkerTree @(Get-CimInstance Win32_Process) $entry)
# Check the selected runtime and databases before disturbing a running service.
& $runtimePython -X utf8 -u $entry --env-file (ProjectPath $EnvFile) --postgres-env-file (ProjectPath $PostgresEnvFile) --media-root (ProjectPath $MediaRoot) --check
if ($LASTEXITCODE -ne 0) { throw 'Runtime preflight failed; no service was stopped.' }
$recordRoot = Join-Path $projectRoot '.scratch/runtime'
$metadataPath = Join-Path $recordRoot "preview-$Port.json"
$listeners = @(Get-NetTCPConnection -LocalPort $Port,$McpPort -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count) {
    if (!$Restart -or !(Test-Path -LiteralPath $metadataPath)) { throw 'Port in use; no process was stopped.' }
    $previous = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
    if ([IO.Path]::GetFullPath($previous.root) -ne $projectRoot) { throw 'Service belongs to another workspace.' }
    $processes = @(Get-CimInstance Win32_Process)
    $launcher = $processes | Where-Object { $_.ProcessId -eq $previous.launcher_pid }
    if (!$launcher -or $launcher.CommandLine -notlike "*$entry*") { throw 'Launcher identity changed.' }
    $owned = [Collections.Generic.HashSet[int]]::new()
    [void]$owned.Add([int]$launcher.ProcessId)
    do {
        $before = $owned.Count
        foreach ($process in $processes) {
            if ($owned.Contains([int]$process.ParentProcessId)) { [void]$owned.Add([int]$process.ProcessId) }
        }
    } while ($owned.Count -ne $before)
    foreach ($listener in $listeners) {
        if (!$owned.Contains([int]$listener.OwningProcess)) { throw 'An unrelated process owns a requested port.' }
    }
    foreach ($process in ($processes | Where-Object { $owned.Contains([int]$_.ProcessId) })) {
        Stop-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
    }
}
New-Item -ItemType Directory -Path $recordRoot -Force | Out-Null
$stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')
$stdout = Join-Path $recordRoot "backend-$stamp.out.log"
$stderr = Join-Path $recordRoot "backend-$stamp.err.log"
$started = Start-Process -FilePath $runtimePython -ArgumentList $baseArgs -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$record = [ordered]@{launcher_pid=$started.Id;root=$projectRoot;runtime=$runtimePython;port=$Port;mcp_port=$McpPort;stdout=$stdout;stderr=$stderr;python_version='3.13';django_version='5.2'}
$record | ConvertTo-Json | Set-Content -LiteralPath $metadataPath -Encoding utf8
$deadline = [DateTime]::UtcNow.AddSeconds(50)
$httpHandler = [System.Net.Http.HttpClientHandler]::new()
$httpHandler.UseProxy = $false
$http = [System.Net.Http.HttpClient]::new($httpHandler)
$http.Timeout = [TimeSpan]::FromSeconds(2)
$backendReady = $false
do {
    if ($started.HasExited) { throw "Backend exited; inspect $stderr" }
    try {
        $health = $http.GetStringAsync("http://127.0.0.1:$McpPort/health").GetAwaiter().GetResult() | ConvertFrom-Json
        $web = $http.GetAsync("http://127.0.0.1:$Port/buyer_support.html").GetAwaiter().GetResult()
        $webOk = [int]$web.StatusCode -eq 200
        $web.Dispose()
        if ($health.status -eq 'ready' -and $webOk) {
            $record.pid = (Get-NetTCPConnection -LocalPort $Port -State Listen).OwningProcess
            $record.mcp_pid = (Get-NetTCPConnection -LocalPort $McpPort -State Listen).OwningProcess
            $record | ConvertTo-Json | Set-Content -LiteralPath $metadataPath -Encoding utf8
            $backendReady = $true
            break
        }
    } catch { }
    Start-Sleep -Milliseconds 300
} while ([DateTime]::UtcNow -lt $deadline)
$http.Dispose()
if (!$backendReady) { throw "Backend readiness timed out; inspect $stderr" }
# Keep profile errors outside the health-probe catch: never report partial readiness.
$profileRecord = Sync-ProfileWorker -Enabled $profileState.enabled -Restart ([bool]$Restart) -ProjectRoot $projectRoot -Python $runtimePython -Entry $entry -BaseArgs $baseArgs -RecordRoot $recordRoot
$record.profile_worker_pid = $profileRecord.launcher_pid
$record.profile_worker_status = $profileRecord.status
$record | ConvertTo-Json | Set-Content -LiteralPath $metadataPath -Encoding utf8
Write-Output "Python 3.13 backend ready: http://127.0.0.1:$Port/buyer_support.html; MCP workers=$($health.workers); profile=$($profileRecord.status)"
