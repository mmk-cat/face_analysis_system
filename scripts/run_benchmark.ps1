param(
    [int]$LatencyMs = 500,
    [int]$Requests = 100,
    [int[]]$Concurrency = @(50, 100)
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$conc = ($Concurrency | ForEach-Object { $_ }) -join " "
python -m benchmarks.benchmark --latency-ms $LatencyMs --requests $Requests --concurrency $conc
exit $LASTEXITCODE
