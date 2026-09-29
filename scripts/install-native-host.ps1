param(
    [switch]$SkipBuild,
    [switch]$SkipRegistry,
    [string]$ArtifactRoot
)

$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$NativeRoot = Join-Path $Root "native_host"
if (-not $ArtifactRoot) {
    $ArtifactRoot = $NativeRoot
}
$ArtifactRoot = [System.IO.Path]::GetFullPath($ArtifactRoot)
$InstallDir = Join-Path $ArtifactRoot "install"
$DistDir = Join-Path $ArtifactRoot "dist"
$BuildDir = Join-Path $ArtifactRoot "build"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$HostScript = Join-Path $Root "native_host\host.py"
$HostExe = Join-Path $DistDir "ycd-helper-control.exe"
$ManifestPath = Join-Path $InstallDir "com.ycd.helper_control.json"
$ConfigPath = Join-Path $InstallDir "config.json"
$ManifestSource = Join-Path $Root "extension\manifest.json"
$RegistryPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.ycd.helper_control"

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Get-ChromiumExtensionId([string]$ManifestKey) {
    $bytes = [Convert]::FromBase64String($ManifestKey)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $digest = $sha.ComputeHash($bytes)
    } finally {
        $sha.Dispose()
    }
    $builder = New-Object System.Text.StringBuilder
    for ($i = 0; $i -lt 16; $i++) {
        [void]$builder.Append([char](97 + ($digest[$i] -shr 4)))
        [void]$builder.Append([char](97 + ($digest[$i] -band 15)))
    }
    return $builder.ToString()
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Virtual environment not found. Run scripts/setup.ps1 first."
}
if (-not (Test-Path -LiteralPath $ManifestSource)) {
    throw "Extension manifest not found."
}

$manifest = Get-Content -LiteralPath $ManifestSource -Raw | ConvertFrom-Json
if (-not $manifest.key) {
    throw "Extension manifest key is missing."
}
$ExtensionId = Get-ChromiumExtensionId $manifest.key
$AllowedOrigin = "chrome-extension://$ExtensionId/"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

if (-not $SkipBuild) {
    New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
    & $Python -m pip install "pyinstaller>=6,<7"
    if ($LASTEXITCODE -ne 0) { throw "Failed to install PyInstaller." }
    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --name ycd-helper-control `
        --distpath $DistDir `
        --workpath $BuildDir `
        --specpath $BuildDir `
        --paths $Root `
        $HostScript
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $HostExe)) {
        throw "Failed to build native helper control host."
    }
}

$config = [ordered]@{
    repo_root = $Root
}
$nativeManifest = [ordered]@{
    name = "com.ycd.helper_control"
    description = "YouTube Downloader helper control"
    path = [System.IO.Path]::GetFullPath($HostExe)
    type = "stdio"
    allowed_origins = @($AllowedOrigin)
}

Write-Utf8NoBom $ConfigPath (($config | ConvertTo-Json -Depth 4) + "`n")
Write-Utf8NoBom $ManifestPath (($nativeManifest | ConvertTo-Json -Depth 4) + "`n")

if (-not $SkipRegistry) {
    New-Item -Path $RegistryPath -Force | Out-Null
    Set-Item -Path $RegistryPath -Value $ManifestPath
}

Write-Host "Native helper control ready."
Write-Host "Extension ID: $ExtensionId"
Write-Host "Manifest: $ManifestPath"
