# test_production_release.ps1
# Production release verification test for BE-028
# Tests missing secrets rejection, production profile presence, migration-job uniqueness,
# readiness-gated traffic, Nginx TLS/security headers, release manifest, and rollback matrix.

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$infraDir = Split-Path -Parent $scriptDir
$repoRoot = Split-Path -Parent $infraDir

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "OpenLibraryOS BE-028: Production Release Verification Test" -ForegroundColor Cyan
Write-Host "Repo Root: $repoRoot" -ForegroundColor Gray
Write-Host "======================================================================" -ForegroundColor Cyan

$pythonExe = "python"
$verifyScript = Join-Path $scriptDir "verify_production_release.py"

if (-not (Test-Path $verifyScript)) {
    Write-Error "Verification script not found: $verifyScript"
    exit 1
}

# Run the Python verification harness
& $pythonExe $verifyScript
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Host "`n[FAIL] Production release verification gates failed." -ForegroundColor Red
    exit $exitCode
} else {
    Write-Host "`n[SUCCESS] All production release verification gates passed." -ForegroundColor Green
    exit 0
}
