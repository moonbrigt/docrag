# 一键启动 DocRAG（acceptance compose）
# 双击运行即可；等价于 docker compose -f docker-compose.acceptance.yml up -d
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
docker compose -p docrag-acceptance -f docker-compose.acceptance.yml up -d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host ''
Write-Host 'DocRAG 已启动：http://127.0.0.1:3302  ' -ForegroundColor Green