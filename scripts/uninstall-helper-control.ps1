$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$NativeRoot = [System.IO.Path]::GetFullPath((Join-Path $Root "native_host"))
$NativePrefix = $NativeRoot.TrimEnd('\') + '\'
$RegistryPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.ycd.helper_control"
$ManifestPath = [System.IO.Path]::GetFullPath((Join-Path $NativeRoot "install\com.ycd.helper_control.json"))

if (Test-Path -LiteralPath $RegistryPath) {
    $RegisteredManifest = Get-ItemPropertyValue -LiteralPath $RegistryPath -Name '(default)'
    $RegisteredManifestPath = [System.IO.Path]::GetFullPath([string]$RegisteredManifest)
    if ([string]::Equals($RegisteredManifestPath, $ManifestPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $RegistryPath -Recurse -Force
    } else {
        Write-Host "Native helper control registration belongs to another checkout; leaving it unchanged."
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
