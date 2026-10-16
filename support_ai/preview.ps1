param(
    [string]$PythonPath = 'E:\miniconda\envs\dadashop\python.exe',
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AgentArguments
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath $PythonPath)) {
    $PythonPath = (Get-Command python -ErrorAction Stop).Source
}
$Host.UI.RawUI.WindowTitle = 'Dadashop Agent Preview'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'
& $PythonPath -X utf8 -u (Join-Path $projectRoot 'manage.py') agent_preview @AgentArguments
if ($LASTEXITCODE -ne 0) { throw "Agent preview exited with code $LASTEXITCODE" }
