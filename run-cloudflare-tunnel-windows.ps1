# Run free Cloudflare Quick Tunnel for local Ozon worker
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$tools = Join-Path $root ".tools"
New-Item -ItemType Directory -Force -Path $tools | Out-Null
$exe = Join-Path $tools "cloudflared.exe"
if (-not (Test-Path $exe)) {
  Write-Host "Downloading cloudflared..."
  Invoke-WebRequest -UseBasicParsing "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $exe
}
Write-Host ""
Write-Host "Keep this window open. Copy the https://...trycloudflare.com URL and send it to ChatGPT." -ForegroundColor Cyan
Write-Host ""
& $exe tunnel --url http://127.0.0.1:8765
