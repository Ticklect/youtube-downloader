param([string]$Executable = "")
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $Executable) {
    $Executable = Join-Path $root 'dist\YouTube Downloader Desktop Beta\YouTube Downloader Desktop.exe'
}
$src = @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class WindowProbe {
  [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
  public delegate bool Callback(IntPtr hwnd, IntPtr parameter);
  [DllImport("user32.dll")] public static extern bool EnumWindows(Callback callback, IntPtr parameter);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out Rect rectangle);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hwnd);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int count);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hwnd, StringBuilder text, int count);
}
'@
Add-Type -TypeDefinition $src -ErrorAction Stop
$process = Start-Process -FilePath $Executable -WorkingDirectory (Split-Path $Executable -Parent) -PassThru
try {
  Start-Sleep -Seconds 3
  if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) { throw 'App exited before window inspection' }
  $found = [Collections.Generic.List[string]]::new()
  $callback = [WindowProbe+Callback]{
    param($hwnd, $parameter)
    [uint32] $owner = 0
    [void] [WindowProbe]::GetWindowThreadProcessId($hwnd, [ref]$owner)
    if ($owner -ne $process.Id) { return $true }
    $rect = New-Object WindowProbe+Rect
    [void] [WindowProbe]::GetWindowRect($hwnd, [ref]$rect)
    $caption = New-Object Text.StringBuilder(256)
    $class = New-Object Text.StringBuilder(256)
    [void] [WindowProbe]::GetWindowText($hwnd, $caption, 256)
    [void] [WindowProbe]::GetClassName($hwnd, $class, 256)
    $found.Add(('HWND={0} visible={1} size={2}x{3} class={4} title={5}' -f $hwnd,[WindowProbe]::IsWindowVisible($hwnd),($rect.Right-$rect.Left),($rect.Bottom-$rect.Top),$class,$caption))
    return $true
  }
  [void] [WindowProbe]::EnumWindows($callback, [IntPtr]::Zero)
  $found | ForEach-Object { Write-Output $_ }
  if ($found.Count -eq 0) { Write-Output 'NO_OWNED_TOP_LEVEL_WINDOWS' }
} finally {
  Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
}
