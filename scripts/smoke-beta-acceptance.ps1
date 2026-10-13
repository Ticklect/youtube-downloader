param(
    [string]$Executable = "",
    [switch]$CaptureMatrix,
    [switch]$MatrixOnly
)
$ErrorActionPreference = 'Stop'
if ($MatrixOnly -and -not $CaptureMatrix) { throw 'MatrixOnly requires CaptureMatrix.' }
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$script = Join-Path $PSScriptRoot 'smoke-window.ps1'
$runRoot = Join-Path $root ('dist\smoke-runs\acceptance-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
Write-Output ('GUI_ACCEPTANCE_ROOT=' + $runRoot)
$caseCount = 0

function Invoke-GuiCase([string]$name, [hashtable]$options) {
    $caseCountAtStart = $script:caseCount
    $script:caseCount = $caseCountAtStart + 1
    $options.Executable = $Executable
    Write-Output ('GUI_CASE_BEGIN=' + $name)
    $records = New-Object 'System.Collections.Generic.List[string]'
    $log = Join-Path $runRoot ($name + '.log')
    try {
        & $script @options | ForEach-Object {
            $record = [string]$_
            $records.Add($record)
            if ($record -match '^(GUI_(SMOKE_PASS|SCREENSHOT|INTERACTION_|RESTORED_|EMPTY_|QUEUE_|FULLSCREEN_|SIZE_|WINDOW_TITLE|ISOLATED_LOCALAPPDATA)|THUMBNAIL_UNAVAILABLE)') {
                Write-Output $record
            }
        }
    } finally {
        [IO.File]::WriteAllLines($log, $records.ToArray(), (New-Object Text.UTF8Encoding($false)))
        Write-Output ('GUI_CASE_LOG=' + $log)
    }
    if (-not @($records | Where-Object { $_ -like 'GUI_SMOKE_PASS*' }).Count -or
        -not @($records | Where-Object { $_ -like 'GUI_SCREENSHOT=*' }).Count) {
        throw ('Smoke case did not confirm native window and screenshot: ' + $name)
    }
    Write-Output ('GUI_CASE_PASS=' + $name)
}

if (-not $MatrixOnly) {
    # First process changes state via UIA; the second process checks persisted
    # selections after a real close and restart with a new PID.
    $restorationRoot = Join-Path $runRoot 'restart'
    Invoke-GuiCase 'interaction' @{
        Preview = 'library'; Theme = 'red'; WindowMode = 'normal'
        SessionRoot = $restorationRoot
        ExerciseControls = $true; ExerciseWindowToggle = $true
    }
    Invoke-GuiCase 'restart' @{
        Preview = 'library'; WindowMode = 'normal'
        SessionRoot = $restorationRoot
        ReuseSession = $true; VerifyRestoredSession = $true
    }
    # UIAutomation InvokePattern calls accessible callbacks directly. This
    # separate case exercises actual native pointer hit-testing so a visible
    # button cannot pass acceptance while ignoring mouse clicks.
    Invoke-GuiCase 'physical-mouse-controls' @{
        Preview = 'library'; Theme = 'red'; WindowMode = 'maximized'
        SessionRoot = (Join-Path $runRoot 'physical-mouse-controls')
        ExerciseControls = $true; PhysicalPrimaryActions = $true
    }
    Invoke-GuiCase 'queue-actions' @{
        Preview = 'queue'; Theme = 'red'; WindowMode = 'normal'
        SessionRoot = (Join-Path $runRoot 'queue-actions')
        ExerciseQueueHistory = $true
    }
    Invoke-GuiCase 'empty-queue' @{
        Preview = 'queue'; Theme = 'red'; WindowMode = 'compact'
        SessionRoot = (Join-Path $runRoot 'empty-queue')
        EmptyState = $true; VerifyEmptyQueue = $true
    }
}

if ($CaptureMatrix) {
    foreach ($case in @(
        @{ Name = 'red-library-normal'; Theme = 'red'; Preview = 'library'; WindowMode = 'normal' },
        @{ Name = 'red-library-compact-long'; Theme = 'red'; Preview = 'library'; WindowMode = 'compact'; LongTitles = $true; ExerciseTitlePopup = $true; CaptureExpandedTitle = $true },
        @{ Name = 'red-library-minimum'; Theme = 'red'; Preview = 'library'; WindowMode = 'minimum' },
        @{ Name = 'red-library-compact-error'; Theme = 'red'; Preview = 'library'; WindowMode = 'compact'; ErrorPreview = 'channel' },
        @{ Name = 'red-setup-normal'; Theme = 'red'; Preview = 'setup'; WindowMode = 'normal' },
        @{ Name = 'red-setup-maximized-empty'; Theme = 'red'; Preview = 'setup'; WindowMode = 'maximized'; EmptyState = $true },
        @{ Name = 'red-queue-normal-long'; Theme = 'red'; Preview = 'queue'; WindowMode = 'normal'; LongTitles = $true; ExerciseTitlePopup = $true; CaptureExpandedTitle = $true },
        @{ Name = 'red-queue-fullscreen'; Theme = 'red'; Preview = 'queue'; WindowMode = 'fullscreen' },
        @{ Name = 'red-queue-compact-active'; Theme = 'red'; Preview = 'queue'; WindowMode = 'compact'; ActiveQueue = $true },
        @{ Name = 'red-queue-history-confirmation'; Theme = 'red'; Preview = 'queue'; WindowMode = 'normal'; CaptureHistoryConfirmation = $true },
        @{ Name = 'mono-library-normal'; Theme = 'mono'; Preview = 'library'; WindowMode = 'normal' },
        @{ Name = 'mono-library-maximized'; Theme = 'mono'; Preview = 'library'; WindowMode = 'maximized' },
        @{ Name = 'mono-setup-compact-review'; Theme = 'mono'; Preview = 'setup'; WindowMode = 'compact'; ExerciseSelectionPopup = $true },
        @{ Name = 'mono-setup-minimum'; Theme = 'mono'; Preview = 'setup'; WindowMode = 'minimum' },
        @{ Name = 'mono-setup-fullscreen-empty'; Theme = 'mono'; Preview = 'setup'; WindowMode = 'fullscreen'; EmptyState = $true },
        @{ Name = 'mono-queue-normal'; Theme = 'mono'; Preview = 'queue'; WindowMode = 'normal' },
        @{ Name = 'mono-queue-compact-empty'; Theme = 'mono'; Preview = 'queue'; WindowMode = 'compact'; EmptyState = $true; VerifyEmptyQueue = $true },
        @{ Name = 'mono-queue-minimum-error'; Theme = 'mono'; Preview = 'queue'; WindowMode = 'minimum'; ErrorPreview = 'queue' }
    )) {
        $settings = @{
            Preview = $case.Preview; Theme = $case.Theme; WindowMode = $case.WindowMode
            SessionRoot = (Join-Path $runRoot $case.Name)
        }
        if ($case.ContainsKey('ErrorPreview')) { $settings.ErrorPreview = $case.ErrorPreview }
        foreach ($optional in @('EmptyState','LongTitles','ExerciseTitlePopup','CaptureExpandedTitle','ExerciseSelectionPopup','VerifyEmptyQueue','ActiveQueue','CaptureHistoryConfirmation')) {
            if ($case.ContainsKey($optional) -and $case[$optional]) { $settings[$optional] = $true }
        }
        Invoke-GuiCase $case.Name $settings
    }
}
Write-Output ('GUI_ACCEPTANCE_PASS=' + $caseCount + ' cases')
