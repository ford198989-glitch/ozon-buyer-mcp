$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    py -3.13 -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
& .\.venv\Scripts\python.exe -m playwright install chromium

Write-Host "Ozon Buyer MCP v0.2 installed."
Write-Host "Run: .\\run-windows.ps1"
