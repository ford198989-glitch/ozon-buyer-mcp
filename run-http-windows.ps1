$ErrorActionPreference = "Stop"
$env:OZON_TRANSPORT = "streamable-http"
$env:OZON_HOST = "0.0.0.0"
$env:OZON_PORT = if ($env:OZON_PORT) { $env:OZON_PORT } else { "8084" }
$env:OZON_HEADLESS = if ($env:OZON_HEADLESS) { $env:OZON_HEADLESS } else { "0" }
& .\.venv\Scripts\ozon-buyer-mcp.exe
