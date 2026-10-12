#Requires -Version 5.1
<#
install.ps1 - installer for claude-hub on Windows.
    irm https://raw.githubusercontent.com/st2l/claude-hub/main/install.ps1 | iex
Re-run it to upgrade. Needs Python 3.11+ with pip; git is not required.
#>

$ErrorActionPreference = 'Stop'
$Source = 'https://github.com/st2l/claude-hub/archive/refs/heads/main.zip'
$CursesReq = 'windows-curses>=2.4.2'

function Say  { param($m) Write-Host "==> $m" -ForegroundColor Cyan }
function Note { param($m) Write-Host "    $m" -ForegroundColor DarkGray }
function Die  { param($m) throw "claude-hub install: $m" }

function Find-Python {
    $probe = 'import sys; print(1 if sys.version_info >= (3, 11) else 0)'
    foreach ($candidate in @(
        @{ Exe = 'py';      Pre = @('-3') },
        @{ Exe = 'python';  Pre = @() },
        @{ Exe = 'python3'; Pre = @() }
    )) {
        if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) { continue }
        $ok = & $candidate.Exe @($candidate.Pre + @('-c', $probe)) 2>$null
        if ($LASTEXITCODE -eq 0 -and $ok -eq '1') { return $candidate }
    }
    return $null
}

$python = Find-Python
if (-not $python) {
    Note 'Get Python from https://python.org/downloads and tick'
    Note '"Add python.exe to PATH", or run: winget install Python.Python.3.13'
    Die 'Python 3.11+ not found'
}
$py = $python.Exe
$pre = $python.Pre

Say "Using Python: $(& $py @pre -c 'import sys; print(sys.executable, sys.version.split()[0])')"

& $py @pre -m pip --version *> $null
if ($LASTEXITCODE -ne 0) {
    Die "pip is unavailable there. Run: $py $pre -m ensurepip --upgrade"
}

# --user is rejected inside a virtualenv, where it is also pointless.
$inVenv = (& $py @pre -c 'import sys; print(sys.prefix != sys.base_prefix)') -eq 'True'
$common = @('-m', 'pip', 'install', '--upgrade', '--disable-pip-version-check')
if (-not $inVenv) { $common += '--user' }

Say 'Installing windows-curses (the TUI needs it; Windows has no stdlib curses)'
& $py @pre @common $CursesReq
if ($LASTEXITCODE -ne 0) { Die "could not install $CursesReq" }

# --force-reinstall --no-deps: the source zip carries no version bump, so this
# is what makes a re-run actually replace the code.
Say 'Installing claude-hub'
& $py @pre @common '--force-reinstall' '--no-deps' $Source
if ($LASTEXITCODE -ne 0) { Die 'pip install failed (see the output above)' }

$scheme = if ($inVenv) { 'venv' } else { 'nt_user' }
$binDir = & $py @pre -c "import sysconfig; print(sysconfig.get_path('scripts', '$scheme'))"
$bin = Join-Path $binDir 'claude-hub.exe'
if (-not (Test-Path $bin)) { Die "pip reported success but $bin is missing" }

if (($env:Path -split ';') -notcontains $binDir) {
    Say "Adding $binDir to your user PATH"
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if (($userPath -split ';') -notcontains $binDir) {
        $prefix = if ([string]::IsNullOrEmpty($userPath)) { '' } else { "$userPath;" }
        [Environment]::SetEnvironmentVariable('Path', "$prefix$binDir", 'User')
    }
    $env:Path = "$env:Path;$binDir"
    Note 'Already-open terminals need a restart to see it.'
}

& $bin -h *> $null
if ($LASTEXITCODE -ne 0) { Die "$bin is installed but will not run" }

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Note 'Claude Code itself is not installed yet. Get it with:'
    Note '  irm https://claude.ai/install.ps1 | iex'
}

Write-Host ''
Say 'Done! Run: claude-hub'
