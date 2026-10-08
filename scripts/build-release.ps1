param(
    [string]$OutputDir,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$Manifest = Get-Content -LiteralPath (Join-Path $Root "extension\manifest.json") -Raw | ConvertFrom-Json
$ExistingIdentitiesPath = Join-Path $Root "extension\browser-identities.json"
$ExistingIdentities = $null
if (Test-Path -LiteralPath $ExistingIdentitiesPath -PathType Leaf) {
    $ExistingIdentities = Get-Content -LiteralPath $ExistingIdentitiesPath -Raw | ConvertFrom-Json
}
$ChromePublicKey = [string]$Manifest.key
if (-not $ChromePublicKey -and $ExistingIdentities) {
    $ChromePublicKey = [string]$ExistingIdentities.key
}
$FirefoxExtensionId = [string]$Manifest.browser_specific_settings.gecko.id
if (-not $FirefoxExtensionId -and $ExistingIdentities) {
    $FirefoxExtensionId = [string]$ExistingIdentities.firefox_id
}
$Version = [string]$Manifest.version
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Extension manifest must have a release version such as 1.0.0."
}

if (-not $OutputDir) {
    $OutputDir = Join-Path $Root "release"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$Browsers = @("Chrome", "Firefox")
$Python = Join-Path $Root ".venv\Scripts\python.exe"

foreach ($Browser in $Browsers) {
    $Label = if ($Browser -eq "Firefox") { "Firefox-Windows-Temporary" } else { "Chrome-Windows" }
    $Archive = Join-Path $OutputDir "YouTube-Downloader-v$Version-$Label.zip"
    if (Test-Path -LiteralPath $Archive) {
        throw "Release package already exists: $Archive. Move or rename it before rebuilding."
    }
}

if (-not $SkipTests) {
    if (-not (Test-Path -LiteralPath $Python)) {
        $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $PythonCommand) {
            throw "Release validation requires Python with the helper dependencies installed."
        }
        $Python = $PythonCommand.Source
    }
    & npm test
    if ($LASTEXITCODE -ne 0) { throw "JavaScript tests failed; release package was not built." }
    $PreviousPluginSetting = $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD
    try {
        $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
        & $Python -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw "Python tests failed; release package was not built." }
    } finally {
        $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = $PreviousPluginSetting
    }
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$OutputPrefix = $OutputDir.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar

function Copy-ReleaseFile([string]$RelativePath) {
    $Source = Join-Path $Root $RelativePath
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
        throw "Release asset missing: $RelativePath"
    }
    $Target = Join-Path $Staging $RelativePath
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Target) | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Target
}

function Write-ReleaseJson([string]$Path, [object]$Value, [int]$Depth) {
    $Json = ($Value | ConvertTo-Json -Depth $Depth) + "`n"
    [System.IO.File]::WriteAllText($Path, $Json, (New-Object System.Text.UTF8Encoding($false)))
}

foreach ($Browser in $Browsers) {
    $Label = if ($Browser -eq "Firefox") { "Firefox-Windows-Temporary" } else { "Chrome-Windows" }
    $Archive = Join-Path $OutputDir "YouTube-Downloader-v$Version-$Label.zip"
    $BuildId = [guid]::NewGuid().ToString("N")
    $Staging = Join-Path $OutputDir ".ycd-stage-$BuildId"
    $TempArchive = Join-Path $OutputDir ".ycd-archive-$BuildId.zip"
try {
    New-Item -ItemType Directory -Path $Staging | Out-Null
    foreach ($item in @("README.md", "LICENSE", "extension\manifest.json", "extension\popup.html", "extension\popup.css", "extension\popup.js", "extension\api.js", "extension\helper-control.js", "extension\job-lifecycle.js", "extension\state.js", "extension\storage-queue.js", "helper\requirements.txt")) {
        Copy-ReleaseFile $item
    }
    foreach ($directory in @("helper", "native_host")) {
        Get-ChildItem -LiteralPath (Join-Path $Root $directory) -File -Filter "*.py" | ForEach-Object {
            Copy-ReleaseFile (Join-Path $directory $_.Name)
        }
    }
    foreach ($scriptName in @("setup.ps1", "start-helper.ps1", "install-native-host.ps1", "uninstall-helper-control.ps1")) {
        Copy-ReleaseFile (Join-Path "scripts" $scriptName)
    }
    foreach ($iconName in @("icon16.png", "icon32.png", "icon48.png", "icon128.png")) {
        Copy-ReleaseFile (Join-Path "extension\icons" $iconName)
    }

    # Package separate manifests so each browser sees only supported identity
    # fields, while the native helper can still register both browser hosts.
    $BrowserManifest = Get-Content -LiteralPath (Join-Path $Staging "extension\manifest.json") -Raw | ConvertFrom-Json
    $Identity = [ordered]@{
        key = $ChromePublicKey
        firefox_id = $FirefoxExtensionId
    }
    if (-not $Identity.key -or -not $Identity.firefox_id) {
        throw "Both Chrome and Firefox extension identities are required."
    }
    Write-ReleaseJson (Join-Path $Staging "extension\browser-identities.json") $Identity 4
    if ($Browser -eq "Chrome") {
        $BrowserManifest.PSObject.Properties.Remove("browser_specific_settings")
    } else {
        $BrowserManifest.PSObject.Properties.Remove("key")
    }
    Write-ReleaseJson (Join-Path $Staging "extension\manifest.json") $BrowserManifest 8

    # Package to a temporary ZIP outside staging so failed builds never leave a
    # partially written public archive, and the ZIP cannot include itself.
    Compress-Archive -Path (Join-Path $Staging '*') -DestinationPath $TempArchive -CompressionLevel Optimal
    if (-not (Test-Path -LiteralPath $TempArchive -PathType Leaf)) {
        throw "Release archive was not created."
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $Zip = [System.IO.Compression.ZipFile]::OpenRead($TempArchive)
    try {
        $Entries = @($Zip.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })
        foreach ($Required in @('README.md', 'extension/manifest.json', 'extension/browser-identities.json', 'scripts/setup.ps1', 'native_host/host.py')) {
            if ($Entries -notcontains $Required) {
                throw "Release ZIP is incomplete: $Required"
            }
        }
    } finally {
        $Zip.Dispose()
    }

    if (Test-Path -LiteralPath $Archive) {
        throw "Release package already exists: $Archive. Move or rename it before rebuilding."
    }
    Move-Item -LiteralPath $TempArchive -Destination $Archive -ErrorAction Stop
    Write-Host "Release archive ready: $Archive"
    # Use .NET rather than Get-FileHash: some Windows PowerShell runners do not
    # expose that cmdlet even though the release ZIP was built successfully.
    $HashAlgorithm = [System.Security.Cryptography.SHA256]::Create()
    $HashStream = [System.IO.File]::OpenRead($Archive)
    try {
        $HashBytes = $HashAlgorithm.ComputeHash($HashStream)
        Write-Host "SHA256: $([System.BitConverter]::ToString($HashBytes).Replace('-', ''))"
    } finally {
        $HashStream.Dispose()
        $HashAlgorithm.Dispose()
    }
} finally {
    $CanonicalStage = [System.IO.Path]::GetFullPath($Staging)
    if (Test-Path -LiteralPath $CanonicalStage) {
        if (-not $CanonicalStage.StartsWith($OutputPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove a staging directory outside the release directory."
        }
        Remove-Item -LiteralPath $CanonicalStage -Recurse -Force
    }
    if (Test-Path -LiteralPath $TempArchive) {
        $CanonicalTemp = [System.IO.Path]::GetFullPath($TempArchive)
        if (-not $CanonicalTemp.StartsWith($OutputPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove a temporary archive outside the release directory."
        }
        Remove-Item -LiteralPath $CanonicalTemp -Force
    }
}
}
