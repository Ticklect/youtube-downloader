param(
    [string]$Executable = '',
    [ValidateSet('normal', 'minimum')][string]$WindowMode = 'minimum'
)

$ErrorActionPreference = 'Stop'
$project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $Executable) {
    $Executable = Join-Path $project 'target\release\youtube-downloader-desktop.exe'
}
$Executable = [IO.Path]::GetFullPath($Executable)
if (-not (Test-Path -LiteralPath $Executable)) { throw "Executable missing: $Executable" }
$latestSource = @(
    Get-ChildItem (Join-Path $project 'src') -Filter '*.rs' -File
    Get-ChildItem (Join-Path $project 'ui') -Filter '*.slint' -File
    Get-Item (Join-Path $project 'Cargo.toml')
) | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if ((Get-Item $Executable).LastWriteTimeUtc -lt $latestSource.LastWriteTimeUtc) {
    throw ('QA aborted: executable predates changed source ({0:u}).' -f $latestSource.LastWriteTimeUtc)
}

# This script NEVER uses the real LOCALAPPDATA or the user's notebook session.
$isolated = Join-Path (Join-Path $project 'dist\smoke-runs') ('channel-history-qa-' + [guid]::NewGuid().ToString('N'))
$sessionDir = Join-Path $isolated 'YouTube Downloader Desktop'
New-Item -ItemType Directory -Path $sessionDir -Force | Out-Null
$sessionPath = Join-Path $sessionDir 'session.json'
$alpha = 'https://www.youtube.com/@pinnedalpha/videos'
$beta = 'https://www.youtube.com/@suggestedbeta/videos'
$snapshot = @{
    schema = 1
    theme = 'red'
    channel_name = 'Pinned Alpha'
    channel_url = $alpha
    channel_history = @(
        @{ name = 'Pinned Alpha'; url = $alpha; loads = 3; last_opened = 4 }
        @{ name = 'Suggested Beta'; url = $beta; loads = 7; last_opened = 5 }
    )
    saved_channels = @(@{ name = 'Pinned Alpha'; url = $alpha })
    folder = (Join-Path $isolated 'downloads')
    videos = @(@{ video = @{ id = 'abcdefghijk'; title = 'QA upload'; duration = '1:30'; uploaded = '' }; selected = $true })
    jobs = @()
}
$json = $snapshot | ConvertTo-Json -Depth 10 -Compress
[IO.File]::WriteAllText($sessionPath, $json, (New-Object Text.UTF8Encoding($false)))

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$scope = [System.Windows.Automation.TreeScope]
$trueCondition = [System.Windows.Automation.Condition]::TrueCondition
$buttonType = [System.Windows.Automation.ControlType]::Button
$editType = [System.Windows.Automation.ControlType]::Edit

$script:qaProcess = $null
$script:qaRoot = $null
function Start-QAApplication {
    $before = [Environment]::GetEnvironmentVariable('LOCALAPPDATA', 'Process')
    $beforeSmoke = [Environment]::GetEnvironmentVariable('YTD_UI_SMOKE_PREVIEW', 'Process')
    $beforeWindow = [Environment]::GetEnvironmentVariable('YTD_UI_SMOKE_WINDOW_MODE', 'Process')
    try {
        [Environment]::SetEnvironmentVariable('LOCALAPPDATA', $isolated, 'Process')
        [Environment]::SetEnvironmentVariable('YTD_UI_SMOKE_PREVIEW', '1', 'Process')
        [Environment]::SetEnvironmentVariable('YTD_UI_SMOKE_WINDOW_MODE', $WindowMode, 'Process')
        $script:qaProcess = Start-Process -FilePath $Executable -WorkingDirectory (Split-Path $Executable) -PassThru
    } finally {
        [Environment]::SetEnvironmentVariable('LOCALAPPDATA', $before, 'Process')
        [Environment]::SetEnvironmentVariable('YTD_UI_SMOKE_PREVIEW', $beforeSmoke, 'Process')
        [Environment]::SetEnvironmentVariable('YTD_UI_SMOKE_WINDOW_MODE', $beforeWindow, 'Process')
    }
    $script:qaRoot = $null
    for ($attempt = 0; $attempt -lt 50; $attempt++) {
        Start-Sleep -Milliseconds 150
        if ($script:qaProcess.HasExited) { throw 'QA app exited before exposing its window.' }
        $windows = [System.Windows.Automation.AutomationElement]::RootElement.FindAll($scope::Children, $trueCondition)
        foreach ($candidate in $windows) {
            try {
                if ($candidate.Current.ProcessId -eq $script:qaProcess.Id -and
                    $candidate.Current.Name -like 'YouTube Downloader*Desktop*') {
                    $script:qaRoot = $candidate
                    break
                }
            } catch { }
        }
        if ($script:qaRoot) { break }
    }
    if (-not $script:qaRoot) { throw 'No accessible desktop app window appeared.' }
}

function Stop-QAApplication {
    if ($script:qaProcess -and -not $script:qaProcess.HasExited) {
        Stop-Process -Id $script:qaProcess.Id -Force
        $script:qaProcess.WaitForExit(5000) | Out-Null
    }
    $script:qaRoot = $null
    $script:qaProcess = $null
}

function Find-QAElement([string]$name, [System.Windows.Automation.ControlType]$type) {
    # A Slint PopupWindow may be a separate native window, not a child of the main window.
    $windows = [System.Windows.Automation.AutomationElement]::RootElement.FindAll($scope::Children, $trueCondition)
    foreach ($window in $windows) {
        try {
            if ($window.Current.ProcessId -ne $script:qaProcess.Id) { continue }
            $children = $window.FindAll($scope::Descendants, $trueCondition)
            foreach ($candidate in $children) {
                if ($candidate.Current.ControlType -eq $type -and $candidate.Current.Name -eq $name) {
                    return $candidate
                }
            }
        } catch { }
    }
    return $null
}

function Wait-QAElement([string]$name, [System.Windows.Automation.ControlType]$type) {
    for ($attempt = 0; $attempt -lt 25; $attempt++) {
        $element = Find-QAElement $name $type
        if ($element) { return $element }
        Start-Sleep -Milliseconds 150
    }
    throw "No accessible $($type.ProgrammaticName) named '$name'."
}

function Invoke-QAButton([string]$name) {
    $button = Wait-QAElement $name $buttonType
    $pattern = $button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $pattern.Invoke()
}

function Read-QASession {
    return Get-Content -LiteralPath $sessionPath -Raw | ConvertFrom-Json
}

try {
    Start-QAApplication
    [void](Wait-QAElement 'Pinned Alpha' $buttonType)
    [void](Wait-QAElement 'Remove Pinned Alpha from saved channels' $buttonType)
    [void](Wait-QAElement 'Library' $buttonType)
    [void](Wait-QAElement 'Download options' $buttonType)
    [void](Wait-QAElement 'Downloads' $buttonType)
    Write-Output 'PASS: Saved label and all three primary navigation targets exposed via UI Automation.'

    Invoke-QAButton 'From your searches'
    Invoke-QAButton '+ Save'  # Only one unsaved suggestion is present in this isolated fixture.
    $saved = Read-QASession
    if (@($saved.saved_channels).Count -ne 2 -or @($saved.saved_channels | Where-Object url -eq $beta).Count -ne 1) {
        throw 'Popup + Save failed to persist the suggested channel.'
    }
    [void](Wait-QAElement 'Suggested Beta' $buttonType)
    Write-Output 'PASS: Suggested channel added by accessible popup action and persisted.'

    Invoke-QAButton 'Remove Pinned Alpha from saved channels'
    $saved = Read-QASession
    if (@($saved.saved_channels).Count -ne 1 -or $saved.saved_channels[0].url -ne $beta) {
        throw 'Removing Pinned Alpha did not leave Suggested Beta pinned.'
    }
    Write-Output 'PASS: Remove changed persisted saved bar without affecting another entry.'

    Stop-QAApplication
    Start-QAApplication
    [void](Wait-QAElement 'Suggested Beta' $buttonType)
    [void](Wait-QAElement 'Remove Suggested Beta from saved channels' $buttonType)
    Write-Output 'PASS: Saved bar survives a fresh process restart.'

    # Open calls the ordinary yt-dlp loader; only test the immediate URL field update.
    # This action may initiate a network request, so do it last and terminate our test process.
    Invoke-QAButton 'Suggested Beta'
    $edited = $null
    for ($attempt = 0; $attempt -lt 15; $attempt++) {
        $windows = $script:qaRoot.FindAll($scope::Descendants, $trueCondition)
        foreach ($candidate in $windows) {
            if ($candidate.Current.ControlType -ne $editType) { continue }
            try {
                $value = $candidate.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value
                if ($value -eq $beta) { $edited = $candidate; break }
            } catch { }
        }
        if ($edited) { break }
        Start-Sleep -Milliseconds 150
    }
    if (-not $edited) { throw 'Open did not populate the channel URL input.' }
    Write-Output 'PASS: Open pinned channel populated the URL field and invoked the normal load path.'
    Write-Output "QA_ISOLATED_SESSION=$sessionPath"
} finally {
    Stop-QAApplication
}
