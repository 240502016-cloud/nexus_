param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8090
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
& "$PSScriptRoot\..\backend\.venv\Scripts\python.exe" -m uvicorn gateway.main:app --host $HostAddress --port $Port --workers 1
