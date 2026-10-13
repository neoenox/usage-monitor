#Requires -Version 5.1
<#
.SYNOPSIS
  Reload the usage-monitor unpacked extension into the real Chrome profile.
  Handle-locked to a window it opens itself; never touches existing tabs.
  Only one verified keystroke (omnibox Enter) with focus verification;
  everything else uses focus-free Invoke/Value patterns. Aborts safely on
  competing input. Prints state lines only. Exit 0 = present and enabled.
#>
param(
  [string]$ExtensionDir = 'C:\gemini-desktop\usage-monitor\browser-extension',
  [string]$ExtensionId = 'eobplfaccjbfdlolmdjnalbedehgljjl',
  [int]$IdleAbortMs = 5000,
  [int]$TimeoutSec = 180
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms

function Get-IdleMs {
  $sig = '[DllImport("user32.dll")] public static extern bool GetLastInputInfo(ref RLI i); public struct RLI { public uint cbSize; public uint dwTime; }'
  if (-not ([System.Management.Automation.PSTypeName]'IdleProbe.Rec').Type) {
    Add-Type -MemberDefinition $sig -Name 'Rec' -Namespace 'IdleProbe'
  }
  $li = New-Object 'IdleProbe.Rec+RLI'
  $li.cbSize = 8
  [IdleProbe.Rec]::GetLastInputInfo([ref]$li) | Out-Null
  return [Environment]::TickCount - $li.dwTime
}

function Test-Quiet { return (Get-IdleMs) -ge $IdleAbortMs }

function Get-ChromeWindows {
  $root = [System.Windows.Automation.AutomationElement]::RootElement
  $cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ClassNameProperty, 'Chrome_WidgetWin_1')
  return $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)
}

function Test-ExtensionPresent {
  $prefs = Join-Path $env:LOCALAPPDATA 'Google\Chrome\User Data\Default\Secure Preferences'
  if (-not (Test-Path $prefs)) { return $false }
  try {
    $data = Get-Content $prefs -Raw -Encoding utf8 | ConvertFrom-Json
    $entry = $data.extensions.settings.$ExtensionId
    if ($null -eq $entry) { return $false }
    return (@($entry.disable_reasons).Count -eq 0)
  } catch { return $false }
}

function Close-OwnWindow([int]$Handle) {
  if ($Handle -eq 0) { return }
  try {
    foreach ($w in Get-ChromeWindows) {
      try { if ($w.Current.NativeWindowHandle -eq $Handle) {
        $w.GetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern).Close()
      } } catch {}
    }
  } catch {}
}

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSec)
$myHandle = 0

try {
  if (Test-ExtensionPresent) { Write-Output 'PRESENT-HEALTHY'; exit 0 }
  if (-not (Test-Quiet)) { Write-Output 'ABORT-USER-ACTIVE'; exit 2 }

  $pre = @()
  foreach ($w in Get-ChromeWindows) { try { $pre += $w.Current.NativeWindowHandle } catch {} }
  Start-Process 'C:/Program Files/Google/Chrome/Application/chrome.exe' '--new-window about:blank'

  $w = $null
  while ([DateTime]::UtcNow -lt $deadline) {
    Start-Sleep -Milliseconds 1000
    foreach ($ww in Get-ChromeWindows) {
      try { $h = $ww.Current.NativeWindowHandle } catch { continue }
      if (($pre -notcontains $h) -and ($h -ne $myHandle)) { $w = $ww; $myHandle = $h }
    }
    if ($w) { break }
  }
  if (-not $w) { Write-Output 'FAIL-NO-WINDOW'; exit 3 }

  # Single verified keystroke: focus MUST be our omnibox before Enter.
  $sigFg = '[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);'
  if (-not ([System.Management.Automation.PSTypeName]'FgUtil.Win').Type) {
    Add-Type -MemberDefinition $sigFg -Name 'Win' -Namespace 'FgUtil'
  }
  if (-not (Test-Quiet)) { throw 'user-active-abort' }
  [FgUtil.Win]::SetForegroundWindow([IntPtr]$myHandle) | Out-Null
  Start-Sleep -Milliseconds 400
  $editCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Edit)
  $nav = $false
  foreach ($e in $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, $editCond)) {
    try {
      $v = $e.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
      if ($v.Current.Value -ne '') { continue }
      $e.SetFocus(); Start-Sleep -Milliseconds 300
      if ([System.Windows.Automation.AutomationElement]::FocusedElement.Current.NativeWindowHandle -ne $e.Current.NativeWindowHandle) { continue }
      $v.SetValue('chrome://extensions'); Start-Sleep -Milliseconds 300
      if ([System.Windows.Automation.AutomationElement]::FocusedElement.Current.NativeWindowHandle -ne $e.Current.NativeWindowHandle) { throw 'user-active-abort' }
      [System.Windows.Forms.SendKeys]::SendWait('{ENTER}'); $nav = $true; break
    } catch { if ($_.Exception.Message -eq 'user-active-abort') { throw } }
  }
  if (-not $nav) { throw 'nav-abort' }
  Start-Sleep -Milliseconds 3000

  $btnCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Button)
  $winCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Window)
  $editC = $editCond

  $loaded = Test-ExtensionPresent
  if (-not $loaded) {
    $invoked = $false
    foreach ($b in $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, $btnCond)) {
      try { $bn = $b.Current.Name } catch { continue }
      if (-not $invoked -and $bn.Length -eq 21 -and $bn.Contains([char]0x8AAD)) {
        $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
        $invoked = $true
      }
    }
    if (-not $invoked) { throw 'no-load-button' }
    Start-Sleep -Milliseconds 2000

    # Focus-free folder commit: bottom field SetValue auto-commits a valid
    # folder; fall back to the Select button while the dialog persists.
    $t0 = [DateTime]::UtcNow
    while (([DateTime]::UtcNow - $t0).TotalSeconds -lt 20) {
      $dlgs = @($w.FindAll([System.Windows.Automation.TreeScope]::Descendants, $winCond) |
        Where-Object { try { $_.Current.Name.Length -eq 21 } catch { $false } })
      if ($dlgs.Count -eq 0) { break }
      $field = $null; $best = -1
      foreach ($e in $dlgs[0].FindAll([System.Windows.Automation.TreeScope]::Descendants, $editC)) {
        try {
          $r = $e.Current.BoundingRectangle
          if ([int]$r.Top -gt $best) { $best = [int]$r.Top; $field = $e }
        } catch {}
      }
      if ($field -and $best -gt 400) {
        try {
          $fv = $field.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
          if ($fv.Current.Value -ne $ExtensionDir) { $fv.SetValue($ExtensionDir) }
        } catch {}
      }
      Start-Sleep -Milliseconds 2000
      $still = @($w.FindAll([System.Windows.Automation.TreeScope]::Descendants, $winCond) |
        Where-Object { try { $_.Current.Name.Length -eq 21 } catch { $false } })
      if ($still.Count -gt 0) {
        foreach ($b in $still[0].FindAll([System.Windows.Automation.TreeScope]::Descendants, $btnCond)) {
          try { $ok = ($b.Current.Name.Length -eq 8) -and $b.Current.IsEnabled } catch { $ok = $false }
          if ($ok) {
            try { $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() } catch {}
            break
          }
        }
        Start-Sleep -Milliseconds 2000
      }
    }

    for ($i = 0; $i -lt 10; $i++) {
      if (Test-ExtensionPresent) { $loaded = $true; break }
      Start-Sleep -Milliseconds 1000
    }
  }

  # Owner windows intact?
  $now = @()
  foreach ($ww in Get-ChromeWindows) { try { $now += $ww.Current.NativeWindowHandle } catch {} }
  $missing = @($pre | Where-Object { $now -notcontains $_ })
  if ($missing.Count -gt 0) { Write-Output 'OWNER-CHANGED' } else { Write-Output 'OWNER-INTACT' }
  if ($loaded) { Write-Output 'LOADED'; exit 0 }
  Write-Output 'FAIL-NOT-LOADED'; exit 4
}
catch {
  $m = $_.Exception.Message
  if ($m -eq 'user-active-abort') { Write-Output 'ABORT-USER-ACTIVE'; exit 2 }
  Write-Output ('FAIL-' + $m)
  exit 5
}
finally {
  Close-OwnWindow $myHandle
}
