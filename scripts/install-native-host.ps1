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
$FirefoxDir = Join-Path $InstallDir "firefox"
$FirefoxManifestPath = Join-Path $FirefoxDir "com.ycd.helper_control.json"
$ConfigPath = Join-Path $InstallDir "config.json"
$ManifestSource = Join-Path $Root "extension\manifest.json"
$IdentitySource = Join-Path $Root "extension\browser-identities.json"
$RegistryPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.ycd.helper_control"
$FirefoxRegistryPath = "HKCU:\Software\Mozilla\NativeMessagingHosts\com.ycd.helper_control"

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
$Identity = $null
if (Test-Path -LiteralPath $IdentitySource -PathType Leaf) {
    $Identity = Get-Content -LiteralPath $IdentitySource -Raw | ConvertFrom-Json
}
$ManifestKey = [string]$manifest.key
if (-not $ManifestKey -and $Identity) {
    $ManifestKey = [string]$Identity.key
}
if (-not $ManifestKey) {
    throw "Extension manifest key is missing."
}
$FirefoxId = [string]$manifest.browser_specific_settings.gecko.id
if (-not $FirefoxId -and $Identity) {
    $FirefoxId = [string]$Identity.firefox_id
}
if ($FirefoxId -notmatch '^[a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+$') {
    throw "Firefox extension ID is missing or invalid."
}
$ExtensionId = Get-ChromiumExtensionId $ManifestKey
$AllowedOrigin = "chrome-extension://$ExtensionId/"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path $FirefoxDir | Out-Null
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

$FirefoxToken = $null
if (Test-Path -LiteralPath $ConfigPath -PathType Leaf) {
    try {
        $ExistingConfig = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
        if ([string]::Equals([string]$ExistingConfig.repo_root, $Root, [System.StringComparison]::OrdinalIgnoreCase) -and
            [string]$ExistingConfig.firefox_token -cmatch '^[A-Za-z0-9+/]{43}=$') {
            $FirefoxToken = [string]$ExistingConfig.firefox_token
        }
    } catch {
        $FirefoxToken = $null
    }
}
if (-not $FirefoxToken) {
    $TokenBytes = New-Object byte[] 32
    $Generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $Generator.GetBytes($TokenBytes)
    } finally {
        $Generator.Dispose()
    }
    $FirefoxToken = [Convert]::ToBase64String($TokenBytes)
}
$config = [ordered]@{
    repo_root = $Root
    firefox_token = $FirefoxToken
}
$nativeManifest = [ordered]@{
    name = "com.ycd.helper_control"
    description = "YouTube Downloader helper control"
    path = [System.IO.Path]::GetFullPath($HostExe)
    type = "stdio"
    allowed_origins = @($AllowedOrigin)
}
$firefoxNativeManifest = [ordered]@{
    name = "com.ycd.helper_control"
    description = "YouTube Downloader helper control"
    path = [System.IO.Path]::GetFullPath($HostExe)
    type = "stdio"
    allowed_extensions = @($FirefoxId)
}

Write-Utf8NoBom $ConfigPath (($config | ConvertTo-Json -Depth 4) + "`n")
Write-Utf8NoBom $ManifestPath (($nativeManifest | ConvertTo-Json -Depth 4) + "`n")
Write-Utf8NoBom $FirefoxManifestPath (($firefoxNativeManifest | ConvertTo-Json -Depth 4) + "`n")

if (-not $SkipRegistry) {
    New-Item -Path $RegistryPath -Force | Out-Null
    Set-Item -Path $RegistryPath -Value $ManifestPath
    New-Item -Path $FirefoxRegistryPath -Force | Out-Null
    Set-Item -Path $FirefoxRegistryPath -Value $FirefoxManifestPath
}

Write-Host "Native helper control ready."
Write-Host "Extension ID: $ExtensionId"
Write-Host "Manifest: $ManifestPath"
Write-Host "Firefox manifest: $FirefoxManifestPath"
