# Create a Windows shortcut that starts the monitor from this checkout.
#
# Usage:
#   .\make-shortcut.ps1                  # shortcut on the Desktop
#   .\make-shortcut.ps1 -StartMenu       # entry in the Start Menu
#   .\make-shortcut.ps1 -Name 'Spark' -Destination D:\links
#
# The shortcut opens Windows Terminal in this folder and runs run.cmd, which
# installs windows-curses on first launch if it is missing.

param(
    [string]$Name = 'VAD-OS Spark Monitor',
    [switch]$StartMenu,
    [string]$Destination
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcher = Join-Path $root 'run.cmd'
if (-not (Test-Path -LiteralPath $launcher)) {
    throw "run.cmd was not found next to this script. Run make-shortcut.ps1 from the repository."
}

if (-not $Destination) {
    $Destination = if ($StartMenu) {
        Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs'
    } else {
        [Environment]::GetFolderPath('Desktop')
    }
}
if (-not (Test-Path -LiteralPath $Destination)) {
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
}

$target = Join-Path $Destination ($Name + '.lnk')

# Windows Terminal keeps the box drawing and Cyrillic glyphs intact; plain
# conhost is used only when Terminal is absent.
$terminal = Get-Command wt -ErrorAction SilentlyContinue
if ($terminal) {
    $exe = $terminal.Source
    $arguments = '-d "' + $root + '" cmd /k run.cmd'
} else {
    $exe = Join-Path $env:SystemRoot 'System32\cmd.exe'
    $arguments = '/k run.cmd'
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($target)
$shortcut.TargetPath = $exe
$shortcut.Arguments = $arguments
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation = $exe + ',0'
$shortcut.Description = 'VAD-OS Spark Monitor'
$shortcut.Save()

Write-Host "Shortcut created: $target"
Write-Host 'First run needs a LiteLLM key: .\run.ps1 --save-key'
