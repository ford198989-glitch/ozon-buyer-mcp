# One-command bootstrap for Ozon Buyer MCP local Windows worker
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Write-Host ""
Write-Host "=== Ozon Buyer MCP: local Windows worker ===" -ForegroundColor Cyan
$Token = Read-Host "Введите OZON worker token"
if ([string]::IsNullOrWhiteSpace($Token)) { throw "Token is required" }
$base = Join-Path $env:USERPROFILE "ozon-buyer-mcp-local"
$zip = Join-Path $env:TEMP "ozon-buyer-mcp-main.zip"
$extract = Join-Path $env:TEMP "ozon-buyer-mcp-extract"
if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
if (Test-Path $zip) { Remove-Item $zip -Force }
New-Item -ItemType Directory -Force -Path $base | Out-Null
Write-Host "Скачиваю последнюю версию проекта..." -ForegroundColor Yellow
Invoke-WebRequest -UseBasicParsing "https://github.com/ford198989-glitch/ozon-buyer-mcp/archive/refs/heads/main.zip" -OutFile $zip
Expand-Archive -Force $zip $extract
$src = Join-Path $extract "ozon-buyer-mcp-main"
Copy-Item (Join-Path $src "*") $base -Recurse -Force
$worker = Join-Path $base "run-local-worker-windows.ps1"
$tunnel = Join-Path $base "run-cloudflare-tunnel-windows.ps1"
Write-Host "Запускаю worker..." -ForegroundColor Yellow
Start-Process powershell.exe -ArgumentList @("-NoExit","-ExecutionPolicy","Bypass","-File",$worker,"-Token",$Token)
Start-Sleep -Seconds 12
Write-Host "Запускаю бесплатный Cloudflare tunnel..." -ForegroundColor Yellow
Start-Process powershell.exe -ArgumentList @("-NoExit","-ExecutionPolicy","Bypass","-File",$tunnel)
Write-Host ""
Write-Host "Откроются два окна PowerShell. НЕ закрывай их во время работы с Ozon." -ForegroundColor Cyan
Write-Host "Во втором окне появится адрес вида https://xxxxx.trycloudflare.com" -ForegroundColor Cyan
Write-Host "Пришли этот адрес в ChatGPT. Остальное он настроит сам." -ForegroundColor Green
