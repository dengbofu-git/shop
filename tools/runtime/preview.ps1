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
$runtimePython = (Resolve-Path -LiteralPath (ProjectPath $Python)).Path
$entry = Join-Path $PSScriptRoot 'backend.py'
$baseArgs = @('-X','utf8','-u',('"'+$entry+'"'),'--env-file',('"'+(ProjectPath $EnvFile)+'"'),
    '--postgres-env-file',('"'+(ProjectPath $PostgresEnvFile)+'"'),'--media-root',('"'+(ProjectPath $MediaRoot)+'"'),
    '--addrport',"127.0.0.1:$Port",'--mcp-port',"$McpPort")
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
            $http.Dispose()
            Write-Output "Python 3.13 backend ready: http://127.0.0.1:$Port/buyer_support.html; MCP workers=$($health.workers)"
            return
        }
    } catch { }
    Start-Sleep -Milliseconds 300
} while ([DateTime]::UtcNow -lt $deadline)
$http.Dispose()
throw "Backend readiness timed out; inspect $stderr"
