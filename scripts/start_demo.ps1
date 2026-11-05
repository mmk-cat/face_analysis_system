param(
    [int]$MockPort = 5100,
    [int]$AppPort = 5003,
    [int]$LatencyMs = 30
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Start-Process -FilePath "python" `
    -ArgumentList "-m", "mock_iflytek.run", "--port", $MockPort, "--latency-ms", $LatencyMs `
    -WorkingDirectory $root | Out-Null

$env:PROVIDER_MODE = "iflytek"
$env:IFLYTEK_BASE_URL = "http://127.0.0.1:$MockPort"
$env:IFLYTEK_APP_ID = "demo-app"
$env:IFLYTEK_API_KEY = "demo-api-key"
$env:API_KEY = "dev-service-key"
$env:APP_PORT = "$AppPort"

Start-Sleep -Seconds 1
python -m app.run
