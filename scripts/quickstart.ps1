# One-shot quickstart for Windows. Run from the repo root:
#   .\scripts\quickstart.ps1
# Prerequisites: Docker Desktop running, Python 3.10+, Node 20.6+.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "[1/4] starting Jaeger (docker compose up -d)..."
docker compose up -d

Write-Host "[2/4] installing the checkpoint engine..."
if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --quiet -e ./checkpoints

Write-Host "[3/4] installing node runtime deps..."
npm ci --no-audit --no-fund

Write-Host "[4/4] running the seeded demo..."
& .\.venv\Scripts\agenttrace.exe demo

Write-Host ""
Write-Host "open http://localhost:16686 -> service 'agenttrace' to explore the traces"
