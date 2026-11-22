# MediaFlow Launch Script (PowerShell)
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Starting MediaFlow Web Application" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Check Python runtime
if (Test-Path ".\.venv\Scripts\python.exe") {
    $pythonCmd = ".\.venv\Scripts\python.exe"
} else {
    $pythonCmd = "python"
}

# Open default browser after a brief delay
Start-Process "http://localhost:8000"

# Start the server
& $pythonCmd server.py 8000
