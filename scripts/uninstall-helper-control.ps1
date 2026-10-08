$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$NativeRoot = [System.IO.Path]::GetFullPath((Join-Path $Root "native_host"))
$NativePrefix = $NativeRoot.TrimEnd('\') + '\'
$BrowserRegistrations = @(
    @{
        registry = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.ycd.helper_control"
        manifest = [System.IO.Path]::GetFullPath((Join-Path $NativeRoot "install\com.ycd.helper_control.json"))
    },
    @{
        registry = "HKCU:\Software\Mozilla\NativeMessagingHosts\com.ycd.helper_control"
        manifest = [System.IO.Path]::GetFullPath((Join-Path $NativeRoot "install\firefox\com.ycd.helper_control.json"))
    }
)
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Controller = Join-Path $NativeRoot "controller.py"
$InstallDir = Join-Path $NativeRoot "install"

if (Test-Path -LiteralPath $Python) {
    & $Python $Controller --prepare-uninstall --repo-root $Root --config-dir $InstallDir
    if ($LASTEXITCODE -ne 0) {
        throw "Refusing to uninstall because the helper could not be safely stopped or verified."
    }
} else {
    $ExpectedHelperHealthy = $false
    try {
        $Health = Invoke-RestMethod -Uri "http://127.0.0.1:17865/health" -Method Get -TimeoutSec 1
        $ExpectedHelperHealthy = $Health.service -eq "youtube-channel-downloader"
    } catch {
        $ExpectedHelperHealthy = $false
    }
    if ($ExpectedHelperHealthy) {
        throw "Helper environment is missing while the downloader helper is still running. Refusing to uninstall because ownership cannot be verified."
    }
}

foreach ($BrowserRegistration in $BrowserRegistrations) {
    $RegistryPath = $BrowserRegistration.registry
    $ManifestPath = $BrowserRegistration.manifest
    if (Test-Path -LiteralPath $RegistryPath) {
        $RegisteredManifest = Get-ItemPropertyValue -LiteralPath $RegistryPath -Name '(default)'
        $RegisteredManifestPath = [System.IO.Path]::GetFullPath([string]$RegisteredManifest)
        if ([string]::Equals($RegisteredManifestPath, $ManifestPath, [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $RegistryPath -Recurse -Force
        } else {
            Write-Host "Native helper control registration belongs to another checkout; leaving it unchanged."
        }
    }
}

foreach ($name in @("install", "dist", "build")) {
    $target = [System.IO.Path]::GetFullPath((Join-Path $NativeRoot $name))
    if (-not $target.StartsWith($NativePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove native host artifact outside the native_host directory."
    }
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

Write-Host "Native helper control registration removed."
