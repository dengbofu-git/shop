# 下载 ECharts 到本地，解决浏览器跟踪防护导致的存储访问被阻止
$url = "https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"
$out = Join-Path $PSScriptRoot "echarts.min.js"
Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing
Write-Host "ECharts 已下载到: $out"
