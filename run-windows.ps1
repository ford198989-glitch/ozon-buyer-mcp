$ErrorActionPreference = "Stop"
$env:OZON_TRANSPORT = if ($env:OZON_TRANSPORT) { $env:OZON_TRANSPORT } else { "stdio" }
$env:OZON_HEADLESS = if ($env:OZON_HEADLESS) { $env:OZON_HEADLESS } else { "0" }
& .\.venv\Scripts\ozon-buyer-mcp.exe
