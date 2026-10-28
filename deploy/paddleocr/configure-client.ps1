param([string]$ServiceUrl = 'http://127.0.0.1:18080')
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$localRoot = Join-Path $repoRoot '.scratch/paddleocr'
$key = [System.IO.File]::ReadAllText((Join-Path $localRoot 'api-key')).Trim()
$ready = Invoke-RestMethod -Uri ($ServiceUrl.TrimEnd('/') + '/ready') -Headers @{Authorization = "Bearer $key"} -TimeoutSec 10
if (-not $ready.ready -or $ready.identity.revision -notmatch '^[0-9a-f]{64}$') {
    throw 'OCR service is not ready or returned an invalid identity.'
}
$lines = @(
    'AI_PADDLEOCR_BASE_URL=http://paddleocr:8080',
    'AI_PADDLEOCR_ALLOW_HTTP_HOSTS=paddleocr',
    'AI_PADDLEOCR_MODEL=PaddleOCR-VL-1.6-0.9B',
    ('AI_PADDLEOCR_REVISION=' + $ready.identity.revision),
    ('AI_PADDLEOCR_API_KEY=' + $key),
    'AI_PADDLEOCR_TIMEOUT_SECONDS=300',
    'AI_PADDLEOCR_MAX_IMAGE_BYTES=10000000',
    'AI_PADDLEOCR_MAX_OUTPUT_TOKENS=4096'
)
[System.IO.File]::WriteAllLines((Join-Path $localRoot 'client.env'), $lines)
$ready | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $localRoot 'service-identity.json') -Encoding utf8
Write-Output ('OCR client configured; revision=' + $ready.identity.revision)
