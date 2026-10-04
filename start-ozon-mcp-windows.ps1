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
Write-Host "Updating local code from GitHub..." -ForegroundColor Yellow

if (Test-Path $tmpZip) { Remove-Item $tmpZip -Force }
if (Test-Path $tmpDir) { Remove-Item $tmpDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $base | Out-Null

Invoke-WebRequest -UseBasicParsing $repoZip -OutFile $tmpZip
Expand-Archive -Force $tmpZip $tmpDir
$src = Join-Path $tmpDir "ozon-buyer-mcp-main"
Copy-Item (Join-Path $src "*") $base -Recurse -Force

function Test-WorkerToken {
    param([string]$Candidate)
    try {
        # An unknown job ID returns 404 only after bearer authentication succeeds.
        $null = Invoke-WebRequest -UseBasicParsing "$relay/result" -Method Post -Headers @{ Authorization = "Bearer $Candidate" } -ContentType "application/json" -Body '{"id":"connector-token-check","response":{}}' -TimeoutSec 15
        return $false
    } catch {
        $reply = $_.Exception.Response
        if ($null -ne $reply) {
            $code = [int]$reply.StatusCode
            if ($code -eq 404) { return $true }
            if ($code -eq 401) { return $false }
        }
        throw "Could not verify worker token with Railway relay: $($_.Exception.Message)"
    }
}

$Token = ""
if (Test-Path $tokenFile) {
    try {
        # DPAPI output contains ASCII characters; Trim removes Set-Content's newline.
        $cipher = (Get-Content $tokenFile -Raw -Encoding ASCII).Trim()
        $secure = ConvertTo-SecureString $cipher
        $Token = [System.Net.NetworkCredential]::new("", $secure).Password
    } catch {
        $Token = ""
    }
}
if (-not [string]::IsNullOrWhiteSpace($Token)) {
    if (-not (Test-WorkerToken $Token)) {
        Write-Host "Saved worker token was rejected by Railway. Copy OZON_WORKER_TOKEN from the ozon-worker-relay service." -ForegroundColor Red
        $Token = ""
    }
}
if ([string]::IsNullOrWhiteSpace($Token)) {
    Write-Host "Enter OZON_WORKER_TOKEN from Railway once. It will be encrypted for this Windows account." -ForegroundColor Yellow
    $secure = Read-Host "OZON worker token" -AsSecureString
    $Token = [System.Net.NetworkCredential]::new("", $secure).Password
    if ([string]::IsNullOrWhiteSpace($Token)) { throw "Worker token is required" }
    if (-not (Test-WorkerToken $Token)) { throw "Relay rejected the token (401). Copy OZON_WORKER_TOKEN from the ozon-worker-relay service and retry." }
    ConvertFrom-SecureString -SecureString $secure | Set-Content -Encoding ASCII $tokenFile
}

$pf86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
$chromeCandidates = @(
    (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
    $(if ($pf86) { Join-Path $pf86 "Google\Chrome\Application\chrome.exe" }),
    (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")
)
$chrome = $chromeCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $chrome) { throw "Google Chrome was not found." }

function Ensure-ChromeCdp {
    $cdpOk = $false
    try {
        $null = Invoke-RestMethod "http://127.0.0.1:9222/json/version" -TimeoutSec 2
        $cdpOk = $true
    } catch {}

    if (-not $cdpOk) {
        Write-Host "Chrome CDP is offline. Starting Chrome..." -ForegroundColor Yellow
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

    if (-not $cdpOk) {
        throw "External Chrome CDP is unavailable at 127.0.0.1:9222"
    }
}

Ensure-ChromeCdp
Write-Host "External Chrome CDP: OK" -ForegroundColor Green

$pythonMode = ""
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonMode = "py"
    & py -3 -m pip install -q -e $base
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonMode = "python"
    & python -m pip install -q -e $base
} else {
    throw "Python 3.12+ was not found."
}
if ($LASTEXITCODE -ne 0) { throw "Python package installation failed (exit code $LASTEXITCODE)." }

$env:OZON_WORKER_TOKEN = $Token
$env:OZON_WORKER_HOST = "127.0.0.1"
$env:OZON_WORKER_PORT = "8765"
$env:OZON_HEADLESS = "0"
$env:OZON_CDP_URL = "http://127.0.0.1:9222"

$localHeaders = @{ Authorization = "Bearer $Token" }

# Always restart the local worker after pulling new code. Otherwise a healthy
# old process would keep running the previous package version indefinitely.
try {
    $listeners = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
    foreach ($listener in $listeners) {
        if ($listener.OwningProcess -and $listener.OwningProcess -ne $PID) {
            Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
    if ($listeners) { Start-Sleep -Milliseconds 800 }
} catch {}

Write-Host "Starting local worker..." -ForegroundColor Yellow
$workerOut = Join-Path $base "worker.stdout.log"
$workerErr = Join-Path $base "worker.stderr.log"
Remove-Item $workerOut, $workerErr -Force -ErrorAction SilentlyContinue
$workerArgs = if ($pythonMode -eq "py") { @("-3", "-m", "ozon_buyer_mcp.worker") } else { @("-m", "ozon_buyer_mcp.worker") }
$workerProcess = Start-Process -FilePath $pythonMode -ArgumentList $workerArgs -PassThru -RedirectStandardOutput $workerOut -RedirectStandardError $workerErr

$localOk = $false
for ($i=0; $i -lt 25; $i++) {
    Start-Sleep -Seconds 1
    try {
        $null = Invoke-RestMethod "http://127.0.0.1:8765/health" -Headers $localHeaders -TimeoutSec 2
        $localOk = $true
        break
    } catch {
        $workerProcess.Refresh()
        if ($workerProcess.HasExited) { break }
    }
}
if (-not $localOk) {
    Write-Host "Worker diagnostic output:" -ForegroundColor Red
    if (Test-Path $workerErr) { Get-Content $workerErr -Tail 30 | ForEach-Object { Write-Host $_ } }
    if (Test-Path $workerOut) { Get-Content $workerOut -Tail 10 | ForEach-Object { Write-Host $_ } }
    throw "Local worker did not start at 127.0.0.1:8765"
}
Write-Host "Local worker: OK" -ForegroundColor Green

try {
    $null = Invoke-RestMethod "$relay/health" -TimeoutSec 10
    Write-Host "Railway relay: OK" -ForegroundColor Green
} catch {
    throw "Railway relay is unreachable. Check VPN routing for ozon-worker-relay-production.up.railway.app"
}

Write-Host ""
Write-Host "CONNECTED. Waiting for marketplace requests from ChatGPT..." -ForegroundColor Green
Write-Host "Keep this window and Chrome open while using Price Hunter." -ForegroundColor Cyan
Write-Host ""

$headers = @{ Authorization = "Bearer $Token" }

while ($true) {
    try {
        $next = Invoke-RestMethod "$relay/next" -Headers $headers -TimeoutSec 35
        if ($next.ok -and $next.job) {
            # Recover transparently if the user closed the external Chrome.
            Ensure-ChromeCdp
            $job = $next.job
            $op = [string]$job.op
            if ($op -notin @("search-dom","market-search-dom","delivery-dom","fetch-json")) {
                $response = @{ ok=$false; error="unsupported operation: $op" }
            } else {
                try {
                    $payloadJson = $job.payload | ConvertTo-Json -Depth 30 -Compress
                    $response = Invoke-RestMethod "http://127.0.0.1:8765/$op" -Method Post -Headers $localHeaders -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($payloadJson)) -TimeoutSec 90
                } catch {
                    $response = @{ ok=$false; error=("local worker error: " + $_.Exception.Message) }
                }
            }
            $resultJson = @{ id=$job.id; response=$response } | ConvertTo-Json -Depth 40 -Compress
            $null = Invoke-RestMethod "$relay/result" -Method Post -Headers $headers -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($resultJson)) -TimeoutSec 30
        }
    } catch {
        $reply = $_.Exception.Response
        if ($null -ne $reply -and [int]$reply.StatusCode -eq 401) {
            throw "Railway rejected the worker token (401). Restart the connector and enter the current OZON_WORKER_TOKEN from ozon-worker-relay."
        }
        Write-Host ("Relay reconnect: " + $_.Exception.Message) -ForegroundColor DarkYellow
        Start-Sleep -Seconds 3
    }
}
