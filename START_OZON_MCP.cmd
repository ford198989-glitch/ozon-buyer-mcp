@echo off
chcp 65001 >nul
title Ozon Buyer MCP - PC Connector
set "PS1=%TEMP%\start-ozon-mcp-windows.ps1"
echo Downloading latest Ozon MCP connector...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/ford198989-glitch/ozon-buyer-mcp/main/start-ozon-mcp-windows.ps1' -OutFile '%PS1%'"
if errorlevel 1 (
  echo Failed to download launcher from GitHub.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
if errorlevel 1 pause
