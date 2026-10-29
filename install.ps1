# VAD-OS Spark Monitor installer for Windows 10/11.
#
# Usage from PowerShell:
#   irm https://raw.githubusercontent.com/FractalRainbowDot/vad-os-spark-monitor/main/install.ps1 | iex
#
# Optional environment variables:
#   SPARK_MONITOR_HOME          data directory (default: %LOCALAPPDATA%\vad-os-spark-monitor)
#   SPARK_MONITOR_BIN           launcher directory (default: <data>\bin)
#   SPARK_MONITOR_NO_PATH_UPDATE=1 to skip updating the user PATH
#   PYTHON                      Python executable (default: py -3 / python)

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Repo = if ($env:SPARK_MONITOR_REPO) { $env:SPARK_MONITOR_REPO } else { 'FractalRainbowDot/vad-os-spark-monitor' }
$Asset = 'spark-monitor.pyz'
$Root = if ($env:SPARK_MONITOR_RELEASE_URL) {
    $env:SPARK_MONITOR_RELEASE_URL.TrimEnd('/')
} else {
    "https://github.com/$Repo/releases/latest/download"
}
$DataDir = if ($env:SPARK_MONITOR_HOME) {
    $env:SPARK_MONITOR_HOME
} else {
    Join-Path $env:LOCALAPPDATA 'vad-os-spark-monitor'
}
$BinDir = if ($env:SPARK_MONITOR_BIN) {
    $env:SPARK_MONITOR_BIN
} else {
    Join-Path $DataDir 'bin'
}
$NoPathUpdate = ($env:SPARK_MONITOR_NO_PATH_UPDATE -eq '1')

function Fail([string]$Message) {
    throw $Message
}

function Resolve-Python {
    $candidates = @()
    if ($env:PYTHON) {
        $command = Get-Command $env:PYTHON -ErrorAction SilentlyContinue
        if ($command) {
            $candidates += $command.Source
        } elseif (Test-Path -LiteralPath $env:PYTHON) {
            $candidates += (Resolve-Path -LiteralPath $env:PYTHON).Path
        }
    }

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
    Fail 'Python 3.10+ not found. Install it from https://www.python.org/downloads/windows/ and try again.'
}

function Quote-PowerShell([string]$Value) {
    return $Value.Replace("'", "''")
}

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
} catch {
    # Older PowerShell may not allow changing the protocol; HTTPS still uses defaults.
}

$Python = Resolve-Python
& $Python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) {
    Fail 'Python 3.10 or newer is required.'
}

& $Python -c "import curses" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Installing the windows-curses package...'
    & $Python -m pip install --user --upgrade windows-curses
    if ($LASTEXITCODE -ne 0) {
        Fail 'Could not install windows-curses. Check pip and the internet connection.'
    }
    & $Python -c "import curses" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Fail 'windows-curses is still unavailable after installation.'
    }
}

$ssh = Get-Command ssh -ErrorAction SilentlyContinue
$sshFallback = Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
if (-not $ssh -and -not (Test-Path -LiteralPath $sshFallback)) {
    Write-Warning 'OpenSSH Client is not installed. Enable it in Windows Optional Features.'
}

$tailscale = Get-Command tailscale -ErrorAction SilentlyContinue
$tailscalePaths = @(Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe')
$programX86 = ${env:ProgramFiles(x86)}
if ($programX86) {
    $tailscalePaths += Join-Path $programX86 'Tailscale\tailscale.exe'
}
if (-not $tailscale -and -not ($tailscalePaths | Where-Object { Test-Path -LiteralPath $_ })) {
    Write-Warning 'Tailscale CLI is not installed. Install Tailscale and sign in to the same tailnet.'
}

$tmp = Join-Path ([IO.Path]::GetTempPath()) ('spark-monitor-install-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp -Force | Out-Null
try {
    $assetPath = Join-Path $tmp $Asset
    $checksumPath = Join-Path $tmp ($Asset + '.sha256')

    Write-Host "Downloading $Root/$Asset ..."
    Invoke-WebRequest -UseBasicParsing -Uri "$Root/$Asset" -OutFile $assetPath
    Invoke-WebRequest -UseBasicParsing -Uri "$Root/$Asset.sha256" -OutFile $checksumPath

    $checksumText = Get-Content -LiteralPath $checksumPath -Raw
    $checksumParts = $checksumText -split '\s+'
    $expected = if ($checksumParts.Count -gt 0) { $checksumParts[0].ToLowerInvariant() } else { '' }
    if ($expected -notmatch '^[0-9a-f]{64}$') {
        Fail 'The published checksum has an invalid format.'
    }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $assetPath).Hash.ToLowerInvariant()
    if ($actual -ne $expected) {
        Fail 'SHA-256 verification failed; installation cancelled.'
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($assetPath)
    try {
        $names = @($zip.Entries | ForEach-Object { $_.FullName })
        if ($names -notcontains '__main__.py') {
            Fail 'The downloaded file is not the monitor archive.'
        }
    } finally {
        $zip.Dispose()
    }

    New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
    New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
    $target = Join-Path $DataDir $Asset
    if (Test-Path -LiteralPath $target) {
        Copy-Item -LiteralPath $target -Destination ($target + '.prev') -Force
    }
    Copy-Item -LiteralPath $assetPath -Destination $target -Force

    $pythonValue = Quote-PowerShell $Python
    $targetValue = Quote-PowerShell $target
    $psLauncher = Join-Path $BinDir 'spark-monitor.ps1'
    $cmdLauncher = Join-Path $BinDir 'spark-monitor.cmd'
    $psContent = @'
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
& '__PYTHON__' '__TARGET__' @args
exit $LASTEXITCODE
'@
    $psContent = $psContent.Replace('__PYTHON__', $pythonValue).Replace('__TARGET__', $targetValue)
    Set-Content -LiteralPath $psLauncher -Value $psContent -Encoding UTF8

    $cmdContent = @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0spark-monitor.ps1" %*
exit /b %errorlevel%
'@
    Set-Content -LiteralPath $cmdLauncher -Value $cmdContent -Encoding ASCII

    if (-not $NoPathUpdate) {
        $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
        if ($null -eq $userPath) {
            $userPath = ''
        }
        $parts = @($userPath.Split(';') | Where-Object { $_ -ne '' })
        if ($parts -notcontains $BinDir) {
            $newPath = if ($userPath) { $userPath.TrimEnd(';') + ';' + $BinDir } else { $BinDir }
            [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
            Write-Host "Added $BinDir to the user PATH."
        }
        if (-not (($env:Path.Split(';') -contains $BinDir))) {
            $env:Path = $env:Path + ';' + $BinDir
        }
    }

    $icacls = Get-Command icacls -ErrorAction SilentlyContinue
    if ($icacls -and $env:USERNAME) {
        & $icacls.Source $DataDir /inheritance:r /grant:r "$env:USERNAME:(OI)(CI)F" |
            Out-Null
    }

    $version = (& $Python $target --version | Select-Object -First 1)
    Write-Host ''
    Write-Host "Installed: $target"
    if ($version) {
        Write-Host "Version: $version"
    }
    Write-Host "Launcher: $cmdLauncher"
    Write-Host ''
    Write-Host 'Next steps:'
    Write-Host '  spark-monitor --save-key'
    Write-Host '  spark-monitor'
    Write-Host 'If the command is not found, open a new PowerShell window.'
} finally {
    if (Test-Path -LiteralPath $tmp) {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
