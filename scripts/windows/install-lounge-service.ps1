<#
.SYNOPSIS
  Run a self-hosted AI Chess Lounge server in the background on Windows.

.DESCRIPTION
  Registers a per-user scheduled task that starts lounge_supervisor.py with pythonw.exe
  (no console window) when you sign in, and re-checks it every five minutes. The
  supervisor restarts the server if it exits or stops answering, caps its memory, and
  never runs twice for the same configuration.

  Nothing runs as administrator and no password is stored: the task runs only while
  you are signed in, exactly like an app in your Startup folder.

.EXAMPLE
  .\install-lounge-service.ps1 -Name private -Config "$env:USERPROFILE\.ai-chess-lounge\private\service.json" -Pythonw C:\path\to\.venv\Scripts\pythonw.exe

.EXAMPLE
  .\install-lounge-service.ps1 -Name private -Uninstall
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $Name,
  [string] $Config,
  [string] $Pythonw,
  [switch] $Uninstall,
  [switch] $NoStart
)
$ErrorActionPreference = 'Stop'
$taskName = "AIChessLounge-$Name"

if ($Uninstall) {
  if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Output "Removed $taskName. The server and its engines stopped with the supervisor."
  } else {
    Write-Output "$taskName is not installed."
  }
  return
}

if (-not $Config -or -not (Test-Path $Config)) { throw "Pass -Config with an existing service.json." }
if (-not $Pythonw -or -not (Test-Path $Pythonw)) { throw "Pass -Pythonw with the path to pythonw.exe." }
$Config = (Resolve-Path $Config).Path
$Pythonw = (Resolve-Path $Pythonw).Path
$supervisor = Join-Path $PSScriptRoot 'lounge_supervisor.py'

$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$supervisor`" --config `"$Config`"" `
  -WorkingDirectory (Split-Path $Config)
$atLogon = New-ScheduledTaskTrigger -AtLogOn -User $user
# A watchdog: if the supervisor itself was ended, this brings it back within five minutes.
# While it is running, the new start is ignored (and the supervisor is single-instance anyway).
$watchdog = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -Hidden

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($atLogon, $watchdog) `
  -Principal $principal -Settings $settings -Force `
  -Description "Keeps the AI Chess Lounge server ($Name) running in the background. Remove with install-lounge-service.ps1 -Name $Name -Uninstall." | Out-Null
Write-Output "Installed $taskName (runs $supervisor at sign-in, no window)."

if (-not $NoStart) {
  Start-ScheduledTask -TaskName $taskName
  Write-Output "Started. Status: & `"$($Pythonw -replace 'pythonw.exe$','python.exe')`" `"$supervisor`" --config `"$Config`" status"
}
