$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.11 or newer is required and was not found on PATH."
}

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.11 or newer is required."
}

if (-not (Test-Path $Venv)) {
    python -m venv $Venv
}

$Python = Join-Path $Venv "Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $Root "helper\requirements.txt")

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Warning "FFmpeg is not on PATH. Install FFmpeg before downloading video/audio."
    Write-Host "Example: winget install Gyan.FFmpeg"
    throw "Setup incomplete: FFmpeg is required for the full video/audio downloader."
} else {
    Write-Host "FFmpeg found."
}

$NativeInstaller = Join-Path $PSScriptRoot "install-native-host.ps1"
& powershell -NoProfile -ExecutionPolicy Bypass -File $NativeInstaller
if ($LASTEXITCODE -ne 0) {
    throw "Setup incomplete: native helper control installation failed."
}

Write-Host "Setup complete. The browser extension can now start and stop the helper."
