param([switch]$BuildRelease, [string]$Tag = '')
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$tools = Join-Path $root 'tools'
$downloads = Join-Path $tools 'downloads'
$bin = Join-Path $tools 'bin'
$dist = Join-Path $root 'dist'
$suffix = ''
if ($Tag) {
    if ($Tag -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$') {
        throw 'Package tag must be 1-40 ASCII letters, digits, periods, underscores or hyphens.'
    }
    $suffix = ' ' + $Tag
}
$portable = Join-Path $dist ('YouTube Downloader Desktop Beta' + $suffix)
$zip = Join-Path $dist ('YouTube-Downloader-Desktop-Beta' + $(if ($Tag) { '-' + $Tag } else { '' }) + '-Windows-x64.zip')
# Packaging is immutable: an earlier beta, smoke executable or user-running
# portable folder must never be replaced by a subsequent build.
if ((Test-Path -LiteralPath $portable) -or (Test-Path -LiteralPath $zip)) {
    throw "Package already exists; supply a new -Tag instead: $portable"
}
foreach ($dir in @($tools, $downloads, $bin, $dist, $portable, (Join-Path $portable 'bin'))) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

function Verified-Download([string]$downloadUri, [string]$checksumUri, [string]$destination, [string]$assetName) {
    $checksumResponse = Invoke-WebRequest -UseBasicParsing -Uri $checksumUri -TimeoutSec 45
    $checksumContent = if ($checksumResponse.Content -is [byte[]]) {
        [Text.Encoding]::UTF8.GetString($checksumResponse.Content)
    } else {
        [string]$checksumResponse.Content
    }
    if ($assetName) {
        $matching = @($checksumContent -split '\r?\n' | Where-Object { $_ -match ('(?i)^[0-9a-f]{64}\s+\*?' + [regex]::Escape($assetName) + '$') })
        if ($matching.Count -ne 1) { throw "Missing exactly one checksum for $assetName" }
        $expected = [regex]::Match($matching[0], '[0-9a-fA-F]{64}').Value.ToUpperInvariant()
    } else {
        $expected = [regex]::Match($checksumContent, '[0-9a-fA-F]{64}').Value.ToUpperInvariant()
    }
    if ($expected.Length -ne 64) { throw "Checksum unavailable for $downloadUri" }
    if (-not (Test-Path -LiteralPath $destination) -or
        (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -ne $expected) {
        Write-Host "Downloading from $downloadUri"
        Invoke-WebRequest -UseBasicParsing -Uri $downloadUri -OutFile $destination -TimeoutSec 300
    }
    $actual = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
    if ($actual -ne $expected) { throw "SHA256 mismatch: $destination" }
    Write-Host "Verified $destination"
}

$ytdlp = Join-Path $downloads 'yt-dlp.exe'
Verified-Download 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe' 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/SHA2-256SUMS' $ytdlp 'yt-dlp.exe'
$ffzip = Join-Path $downloads 'ffmpeg-release-essentials.7z'
Verified-Download 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.7z' 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.7z.sha256' $ffzip ''

$denoZip = Join-Path $downloads 'deno-x86_64-pc-windows-msvc.zip'
Verified-Download 'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip' 'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip.sha256sum' $denoZip ''
$deno = Join-Path $bin 'deno.exe'
if (-not (Test-Path -LiteralPath $deno)) {
    $denoExtract = Join-Path $tools 'deno-extract'
    Expand-Archive -LiteralPath $denoZip -DestinationPath $denoExtract -Force
    $denoCandidates = @(Get-ChildItem -LiteralPath $denoExtract -File -Recurse -Filter 'deno.exe')
    if ($denoCandidates.Count -ne 1) { throw 'Deno package did not contain one deno.exe' }
    Copy-Item -LiteralPath $denoCandidates[0].FullName -Destination $deno -Force
}

$ff = Join-Path $bin 'ffmpeg.exe'
$probe = Join-Path $bin 'ffprobe.exe'
if (-not (Test-Path -LiteralPath $ff) -or -not (Test-Path -LiteralPath $probe)) {
    $extract = Join-Path $tools 'ffmpeg-extract'
    New-Item -ItemType Directory -Path $extract -Force | Out-Null
    & "$env:SystemRoot\System32\tar.exe" -x -f $ffzip -C $extract
    if ($LASTEXITCODE -ne 0) { throw 'Unable to unpack verified FFmpeg 7z archive.' }
    $ffCandidates = @(Get-ChildItem -LiteralPath $extract -File -Recurse -Filter 'ffmpeg.exe')
    $probeCandidates = @(Get-ChildItem -LiteralPath $extract -File -Recurse -Filter 'ffprobe.exe')
    if ($ffCandidates.Count -ne 1 -or $probeCandidates.Count -ne 1) { throw 'Unexpected FFmpeg ZIP structure' }
    Copy-Item -LiteralPath $ffCandidates[0].FullName -Destination $ff -Force
    Copy-Item -LiteralPath $probeCandidates[0].FullName -Destination $probe -Force
    $license = @(Get-ChildItem -LiteralPath $extract -File -Recurse | Where-Object { $_.Name -match '^LICENSE(\.txt)?$' } | Select-Object -First 1)
    if ($license.Count) { Copy-Item -LiteralPath $license[0].FullName -Destination (Join-Path $bin 'FFmpeg-LICENSE.txt') -Force }
}
Copy-Item -LiteralPath $ytdlp -Destination (Join-Path $bin 'yt-dlp.exe') -Force

$cargo = Join-Path $env:USERPROFILE '.cargo\bin\cargo.exe'
if ($BuildRelease) {
    if (-not (Test-Path $cargo)) { throw 'Rust toolchain unavailable' }
    Push-Location $root
    try {
        & $cargo build --release --locked
        if ($LASTEXITCODE -ne 0) { throw 'Rust release build failed' }
    } finally { Pop-Location }
}

$executable = Join-Path $root 'target\release\youtube-downloader-desktop.exe'
if (-not (Test-Path $executable)) { throw 'Release executable not found. Run cargo build --release.' }
Copy-Item -LiteralPath $executable -Destination (Join-Path $portable 'YouTube Downloader Desktop.exe') -Force
foreach ($name in @('yt-dlp.exe','ffmpeg.exe','ffprobe.exe','deno.exe')) {
    Copy-Item -LiteralPath (Join-Path $bin $name) -Destination (Join-Path (Join-Path $portable 'bin') $name) -Force
}
if (Test-Path (Join-Path $bin 'FFmpeg-LICENSE.txt')) {
    Copy-Item -LiteralPath (Join-Path $bin 'FFmpeg-LICENSE.txt') -Destination (Join-Path $portable 'FFmpeg-LICENSE.txt') -Force
}
Copy-Item -LiteralPath (Join-Path $root 'README.md') -Destination (Join-Path $portable 'README.txt') -Force
Copy-Item -LiteralPath (Join-Path $root 'LICENSE') -Destination (Join-Path $portable 'LICENSE.txt') -Force
Compress-Archive -LiteralPath $portable -DestinationPath $zip -CompressionLevel Optimal
Write-Host "Portable app built: $zip"
Get-FileHash -LiteralPath $zip -Algorithm SHA256 | Format-List
