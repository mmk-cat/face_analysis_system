param(
    [switch]$Install
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if ($Install) {
    python -m pip install -r requirements.txt
}
python -m pytest -q
exit $LASTEXITCODE
