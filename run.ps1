# Launch VAD-OS Spark Monitor straight from this checkout.
#
#   .\run.cmd               start the monitor
#   .\run.cmd --save-key    store the LiteLLM key
#
# There is no separate setup step: if windows-curses is missing, this launcher
# installs it with pip (user site, or the active virtual environment) and then
# starts the monitor from source.  Dependencies are listed in requirements.txt.

Set-StrictMode -Version Latest
# Native commands write progress and tracebacks to stderr; with 'Stop' Windows
# PowerShell turns that into a terminating error, so it is handled explicitly.
$ErrorActionPreference = 'Continue'

function Resolve-Python {
    $candidates = @()
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $path = & $py.Source -3 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $path) {
            $candidates += $path.Trim()
        }
    }
    foreach ($name in @('python', 'python3')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $command -or $command.Source -like '*\WindowsApps\*') {
            continue
        }
        $path = & $command.Source -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $path) {
            $candidates += $path.Trim()
        }
    }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw 'Python 3.10+ not found. Install it from https://www.python.org/downloads/windows/ and run again.'
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Resolve-Python

& $python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw 'Python 3.10 or newer is required.'
}

# Checking for the compiled _curses module never raises, so no traceback noise.
& $python -c "import importlib.util as u, sys; sys.exit(0 if u.find_spec('_curses') else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host 'First run: installing windows-curses...'
    $venv = & $python -c "import sys; print('1' if sys.prefix != sys.base_prefix else '0')"
    $pipArgs = @('-m', 'pip', 'install', '--upgrade', '--disable-pip-version-check')
    if ($venv -ne '1') {
        $pipArgs += '--user'
    }
    $pipArgs += 'windows-curses'
    & $python @pipArgs
    if ($LASTEXITCODE -ne 0) {
        throw 'pip could not install windows-curses. Check the internet connection and try again.'
    }
    & $python -c "import curses"
    if ($LASTEXITCODE -ne 0) {
        throw 'windows-curses is still unavailable after installation.'
    }
}

$env:PYTHONUTF8 = '1'
& $python (Join-Path $root '__main__.py') @args
exit $LASTEXITCODE
