# Ozon Buyer MCP - Windows one-command connector
# ChatGPT -> Railway MCP -> Railway relay -> this Windows PC -> external Google Chrome -> Ozon
# No secrets are embedded in this file or stored in GitHub/Yandex Disk.

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$repoZip = "https://github.com/ford198989-glitch/ozon-buyer-mcp/archive/refs/heads/main.zip"
$relay = "https://ozon-worker-relay-production.up.railway.app"
$base = Join-Path $env:USERPROFILE "ozon-buyer-mcp-local"
$tmpZip = Join-Path $env:TEMP "ozon-buyer-mcp-main.zip"
$tmpDir = Join-Path $env:TEMP "ozon-buyer-mcp-extract"
$profile = Join-Path $env:USERPROFILE "ozon-buyer-mcp-cdp-profile"
$tokenFile = Join-Path $base ".worker-token.dpapi"

Write-Host ""
Write-Host "=== Ozon Buyer MCP: PC connector ===" -ForegroundColor Cyan
Write-Host "Обновляю локальный код из GitHub..." -ForegroundColor Yellow

if (Test-Path $tmpZip) { Remove-Item $tmpZip -Force }
if (Test-Path $tmpDir) { Remove-Item $tmpDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $base | Out-Null

Invoke-WebRequest -UseBasicParsing $repoZip -OutFile $tmpZip
Expand-Archive -Force $tmpZip $tmpDir
$src = Join-Path $tmpDir "ozon-buyer-mcp-main"
Copy-Item (Join-Path $src "*") $base -Recurse -Force

if (Test-Path $tokenFile) {
    try {
        $secure = Get-Content $tokenFile -Raw | ConvertTo-SecureString
        $Token = [System.Net.NetworkCredential]::new("", $secure).Password
    } catch {
        Remove-Item $tokenFile -Force -ErrorAction SilentlyContinue
        $Token = ""
    }
} else {
    $Token = ""
}

if ([string]::IsNullOrWhiteSpace($Token)) {
    Write-Host "Первый запуск: введи OZON worker token. Он сохранится локально через Windows DPAPI." -ForegroundColor Yellow
    $secure = Read-Host "OZON worker token" -AsSecureString
    $Token = [System.Net.NetworkCredential]::new("", $secure).Password
    if ([string]::IsNullOrWhiteSpace($Token)) { throw "Worker token is required" }
    $secure | ConvertFrom-SecureString | Set-Content -Encoding UTF8 $tokenFile
}

$pf86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
$chromeCandidates = @(
    (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
    $(if ($pf86) { Join-Path $pf86 "Google\Chrome\Application\chrome.exe" }),
    (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")
)
$chrome = $chromeCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $chrome) { throw "Google Chrome не найден." }

$cdpOk = $false
try {
    $null = Invoke-RestMethod "http://127.0.0.1:9222/json/version" -TimeoutSec 2
    $cdpOk = $true
} catch {}

if (-not $cdpOk) {
    Write-Host "Запускаю обычный Google Chrome с CDP на 9222..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $profile | Out-Null
    Start-Process $chrome -ArgumentList @(
        "--remote-debugging-port=9222",
        "--remote-debugging-address=127.0.0.1",
        "--user-data-dir=$profile",
        "https://www.ozon.ru/"
    )
    for ($i=0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        try {
            $null = Invoke-RestMethod "http://127.0.0.1:9222/json/version" -TimeoutSec 2
            $cdpOk = $true
            break
        } catch {}
    }
}
if (-not $cdpOk) { throw "External Chrome CDP недоступен на 127.0.0.1:9222" }
Write-Host "External Chrome CDP: OK" -ForegroundColor Green

$pythonMode = ""
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonMode = "py"
    & py -3 -m pip install -q -e $base
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonMode = "python"
    & python -m pip install -q -e $base
} else {
    throw "Python 3.12+ не найден."
}

$env:OZON_WORKER_TOKEN = $Token
$env:OZON_WORKER_HOST = "127.0.0.1"
$env:OZON_WORKER_PORT = "8765"
$env:OZON_HEADLESS = "0"
$env:OZON_CDP_URL = "http://127.0.0.1:9222"

$localHeaders = @{ Authorization = "Bearer $Token" }
$localOk = $false
try {
    $null = Invoke-RestMethod "http://127.0.0.1:8765/health" -Headers $localHeaders -TimeoutSec 2
    $localOk = $true
} catch {}

if (-not $localOk) {
    Write-Host "Запускаю локальный worker..." -ForegroundColor Yellow
    $cmd = if ($pythonMode -eq "py") { "Set-Location '$base'; py -3 -m ozon_buyer_mcp.worker" } else { "Set-Location '$base'; python -m ozon_buyer_mcp.worker" }
    Start-Process powershell.exe -ArgumentList @("-NoExit","-ExecutionPolicy","Bypass","-Command",$cmd)
    for ($i=0; $i -lt 25; $i++) {
        Start-Sleep -Seconds 1
        try {
            $null = Invoke-RestMethod "http://127.0.0.1:8765/health" -Headers $localHeaders -TimeoutSec 2
            $localOk = $true
            break
        } catch {}
    }
}
if (-not $localOk) { throw "Local worker не отвечает на 127.0.0.1:8765" }
Write-Host "Local worker: OK" -ForegroundColor Green

try {
    $null = Invoke-RestMethod "$relay/health" -TimeoutSec 10
    Write-Host "Railway relay: OK" -ForegroundColor Green
} catch {
    throw "Railway relay недоступен. Проверь маршрут VPN для точного домена ozon-worker-relay-production.up.railway.app"
}

Write-Host ""
Write-Host "CONNECTED. Waiting for Ozon requests from ChatGPT..." -ForegroundColor Green
Write-Host "Не закрывай это окно и внешний Chrome во время работы." -ForegroundColor Cyan
Write-Host ""

$headers = @{ Authorization = "Bearer $Token" }

while ($true) {
    try {
        $next = Invoke-RestMethod "$relay/next" -Headers $headers -TimeoutSec 35
        if ($next.ok -and $next.job) {
            $job = $next.job
            $op = [string]$job.op
            if ($op -notin @("search-dom","delivery-dom","fetch-json")) {
                $response = @{ ok=$false; error="unsupported operation: $op" }
            } else {
                try {
                    $payloadJson = $job.payload | ConvertTo-Json -Depth 30 -Compress
                    $response = Invoke-RestMethod "http://127.0.0.1:8765/$op" -Method Post -Headers $localHeaders -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($payloadJson)) -TimeoutSec 120
                } catch {
                    $response = @{ ok=$false; error=("local worker error: " + $_.Exception.Message) }
                }
            }
            $resultJson = @{ id=$job.id; response=$response } | ConvertTo-Json -Depth 40 -Compress
            $null = Invoke-RestMethod "$relay/result" -Method Post -Headers $headers -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($resultJson)) -TimeoutSec 30
        }
    } catch {
        Write-Host ("Relay reconnect: " + $_.Exception.Message) -ForegroundColor DarkYellow
        Start-Sleep -Seconds 3
    }
}
