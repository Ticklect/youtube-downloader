$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"

if (-not (Test-Path $Venv)) {
    python -m venv $Venv
}

$Python = Join-Path $Venv "Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $Root "helper\requirements.txt")

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Warning "FFmpeg is not on PATH. Install FFmpeg before downloading video/audio."
    Write-Host "Example: winget install Gyan.FFmpeg"
} else {
    Write-Host "FFmpeg found."
}

Write-Host "Setup complete. Start the helper with:"
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\start-helper.ps1"
