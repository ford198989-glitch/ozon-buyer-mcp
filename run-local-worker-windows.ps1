# Run local Ozon worker on Windows
param([Parameter(Mandatory=$true)][string]$Token)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$env:OZON_WORKER_TOKEN = $Token
$env:OZON_WORKER_HOST = "127.0.0.1"
$env:OZON_WORKER_PORT = "8765"
$env:OZON_HEADLESS = "0"
if (Get-Command py -ErrorAction SilentlyContinue) {
  py -3 -m pip install -e .
  py -3 -m playwright install chromium
  py -3 -m ozon_buyer_mcp.worker
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  python -m pip install -e .
  python -m playwright install chromium
  python -m ozon_buyer_mcp.worker
} else {
  throw "Python 3.12+ not found"
}
