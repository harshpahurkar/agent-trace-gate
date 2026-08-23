# The full local gate — everything a CI job would have run, on your machine.
#
#   .\scripts\gate.ps1
#
# Runs the seeded proof (both detection paths), the unit tests, and the
# provenance-ledger gate. Exits nonzero if anything fails.

Set-Location (Split-Path -Parent $PSScriptRoot)

if (Test-Path ".venv\Scripts\agenttrace.exe") {
    $agenttrace = ".\.venv\Scripts\agenttrace.exe"
    $py = ".\.venv\Scripts\python.exe"
} else {
    $agenttrace = "agenttrace"
    $py = "python"
}

$status = 0
function Step($label, $block) {
    Write-Host ""
    Write-Host "-- $label ---------------------------------------"
    & $block
    if ($LASTEXITCODE -ne 0) { $script:status = 1 }
}

Step "seeded proof (static checkpoints)"       { & $agenttrace demo --report ci }
Step "seeded proof (runtime detonation paths)" { & $agenttrace demo --skip-static --report ci }
Step "unit tests"                              { & $py -m pytest tests -q }
Step "ledger gate"                             { & $agenttrace check --report ci }

Write-Host ""
if ($status -eq 0) { Write-Host "gate: PASS" } else { Write-Host "gate: FAIL" }
exit $status
