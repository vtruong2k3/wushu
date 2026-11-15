<#
.SYNOPSIS
  One-command quality gate for taiji_ai (task P0.05, AGENTS.md section 7).
.DESCRIPTION
  Runs lint, format, type, lock, test, web and repository-hygiene checks. Keeps going after a failure and
  prints a summary. Exit: 0 pass, 1 a check failed, 2 environment/usage error (nothing run).
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File tools\check.ps1 -NoGpu
#>
[CmdletBinding()]
param(
    [switch]$NoGpu,
    [switch]$SkipWeb,
    [switch]$DryRun,
    [string]$Root = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-TaijiRoot([string]$SpecifiedRoot) {
    if ($SpecifiedRoot -ne '') {
        $candidate = (Resolve-Path -LiteralPath $SpecifiedRoot -ErrorAction SilentlyContinue)
        if ($null -eq $candidate) {
            return $SpecifiedRoot
        }
        return $candidate.ProviderPath
    }
    return (Split-Path -Parent $PSScriptRoot)
}

function New-Step([int]$Number, [string]$Name, [string]$Dir, [string]$Exe, [string[]]$Arguments, [string]$SkipReason = '') {
    return [pscustomobject]@{
        Number     = $Number
        Name       = $Name
        Dir        = $Dir
        Exe        = $Exe
        Args       = $Arguments
        SkipReason = $SkipReason
    }
}

function Get-UvLauncher {
    # 'py -3.12 -m uv' when the py launcher exists, else 'uv' on PATH. Shared by the uv-lock step and preflight,
    # so preflight verifies exactly the command the step will run.
    if (Get-Command 'py' -ErrorAction SilentlyContinue) {
        return [pscustomobject]@{ Exe = 'py'; Prefix = @('-3.12', '-m', 'uv') }
    }
    return [pscustomobject]@{ Exe = 'uv'; Prefix = @() }
}

function Get-Steps([bool]$NoGpuFlag, [bool]$SkipWebFlag) {
    # Every python step runs in Dir '.' (the taiji_ai root), so the interpreter path stays relative to it.
    # The plan therefore never prints an absolute (personal) path.
    $pythonExe = '.venv\Scripts\python.exe'
    $repoHygieneScript = Join-Path 'tools' 'repo_hygiene.py'

    $uv = Get-UvLauncher
    $uvExe = $uv.Exe
    $uvArgs = @($uv.Prefix) + @('lock', '--check')

    $pytestArgs = @('-m', 'pytest', '-rs')
    if ($NoGpuFlag) {
        $pytestArgs += @('-m', 'not gpu')
    }

    $webSkip = ''
    if ($SkipWebFlag) {
        $webSkip = 'skipped via -SkipWeb'
    }

    $steps = @(
        (New-Step 1  'uv-lock'      '.'   $uvExe      $uvArgs),
        (New-Step 2  'ruff-check'   '.'   $pythonExe  @('-m', 'ruff', 'check', 'src', 'tests', 'tools')),
        (New-Step 3  'ruff-format'  '.'   $pythonExe  @('-m', 'ruff', 'format', '--check', 'src', 'tests', 'tools')),
        (New-Step 4  'mypy'         '.'   $pythonExe  @('-m', 'mypy', 'src')),
        (New-Step 5  'pytest'       '.'   $pythonExe  $pytestArgs),
        (New-Step 6  'web-lint'     'web' 'pnpm.cmd'  @('lint')      $webSkip),
        (New-Step 7  'web-typecheck' 'web' 'pnpm.cmd' @('typecheck') $webSkip),
        (New-Step 8  'web-test'     'web' 'pnpm.cmd'  @('test')      $webSkip),
        (New-Step 9  'web-build'    'web' 'pnpm.cmd'  @('build')     $webSkip),
        (New-Step 10 'repo-hygiene' '.'   $pythonExe  @($repoHygieneScript))
    )
    return $steps
}

function Write-StepPlan($Steps) {
    foreach ($s in $Steps) {
        if ($s.SkipReason -ne '') {
            Write-Output ("SKIP|{0}|{1}|{2}" -f $s.Number, $s.Name, $s.SkipReason)
        } else {
            $cmdLine = ($s.Exe + ' ' + ($s.Args -join ' ')).Trim()
            Write-Output ("STEP|{0}|{1}|{2}|{3}" -f $s.Number, $s.Name, $s.Dir, $cmdLine)
        }
    }
}

function Invoke-SilentProcess([string]$Exe, [string]$Arguments) {
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $Exe
        $psi.Arguments = $Arguments
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($psi)
        $stdout = $proc.StandardOutput.ReadToEnd()
        $stderr = $proc.StandardError.ReadToEnd()
        $proc.WaitForExit()
        return [pscustomobject]@{
            ExitCode = $proc.ExitCode
            StdOut   = $stdout
            StdErr   = $stderr
        }
    } catch {
        return [pscustomobject]@{
            ExitCode = -1
            StdOut   = ''
            StdErr   = $_.Exception.Message
        }
    }
}

function Get-ToolVersion([string]$Exe, [string]$Arguments) {
    # First non-empty output line of '<exe> <arguments>' for the header. A failure is shown, never hidden.
    $proc = Invoke-SilentProcess $Exe $Arguments
    if ($proc.ExitCode -ne 0) {
        return ('unavailable (exit {0})' -f $proc.ExitCode)
    }
    $line = @($proc.StdOut -split "`r?`n" | Where-Object { $_.Trim() -ne '' }) | Select-Object -First 1
    if ($null -eq $line) {
        return 'unknown (no output)'
    }
    return $line.Trim()
}

function Test-Preflight([string]$TaijiRoot, [bool]$SkipWebFlag) {
    $errors = @()

    $pyproject = Join-Path $TaijiRoot 'pyproject.toml'
    $checkScript = Join-Path $TaijiRoot 'tools\check.ps1'
    if ((-not (Test-Path -LiteralPath $pyproject)) -or (-not (Test-Path -LiteralPath $checkScript))) {
        $errors += ("taiji_ai root not found at '{0}' (expected pyproject.toml and tools\check.ps1)" -f $TaijiRoot)
    }

    $pythonExe = Join-Path $TaijiRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        $errors += "Python env missing: run 'py -3.12 -m uv sync' in taiji_ai"
    }

    $uv = Get-UvLauncher
    $uvVersionArgs = (@($uv.Prefix) + @('--version')) -join ' '
    $uvProc = Invoke-SilentProcess $uv.Exe $uvVersionArgs
    if ($uvProc.ExitCode -ne 0) {
        $errors += ("uv not usable ('{0} {1}' failed): py -3.12 -m pip install --user uv" -f $uv.Exe, $uvVersionArgs)
    }

    if (-not (Get-Command 'git' -ErrorAction SilentlyContinue)) {
        $errors += "git not found on PATH"
    } else {
        $gitProc = Invoke-SilentProcess 'git' ("-C `"{0}`" rev-parse --show-toplevel" -f $TaijiRoot)
        if ($gitProc.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($gitProc.StdOut)) {
            $errors += "taiji_ai is not inside a git repository work tree"
        }
    }

    if (-not $SkipWebFlag) {
        $pnpmCmd = Get-Command 'pnpm.cmd' -ErrorAction SilentlyContinue
        if ($null -eq $pnpmCmd) {
            $errors += "pnpm not found (Node >= 24 + pnpm); or use -SkipWeb for a partial run"
        }

        $nodeCmd = Get-Command 'node' -ErrorAction SilentlyContinue
        if ($null -eq $nodeCmd) {
            $errors += "Node not found (Node >= 24 required); or use -SkipWeb for a partial run"
        } else {
            $nodeProc = Invoke-SilentProcess 'node' '--version'
            $nodeVerRaw = $nodeProc.StdOut
            if ($nodeVerRaw -match '^v?(\d+)') {
                $major = [int]$matches[1]
                if ($major -lt 24) {
                    $errors += ("Node {0} found, >= 24 required; or use -SkipWeb for a partial run" -f $nodeVerRaw.Trim())
                }
            }
        }

        $webNodeModules = Join-Path $TaijiRoot 'web\node_modules'
        if (-not (Test-Path -LiteralPath $webNodeModules)) {
            $errors += "web deps missing: cd web; pnpm install --frozen-lockfile"
        }
    }

    return $errors
}

function Invoke-Step($Step, [string]$TaijiRoot, [int]$Total) {
    $targetDir = Join-Path $TaijiRoot $Step.Dir
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $exitCode = 0
    $prevLocation = Get-Location

    Write-Host ("==> [{0}/{1}] {2} ({3})" -f $Step.Number, $Total, $Step.Name, $Step.Dir) -ForegroundColor Cyan
    try {
        Set-Location -LiteralPath $targetDir
        $global:LASTEXITCODE = 0
        & $Step.Exe @($Step.Args) | Out-Host
        $exitCode = $global:LASTEXITCODE
    } catch {
        Write-Host ("Execution error: {0}" -f $_.Exception.Message) -ForegroundColor Red
        $exitCode = 1
    } finally {
        Set-Location -LiteralPath $prevLocation
    }
    $sw.Stop()

    $passed = ($exitCode -eq 0)
    return [pscustomobject]@{
        Name     = $Step.Name
        Passed   = $passed
        Duration = $sw.Elapsed.TotalSeconds
        Skipped  = $false
    }
}

function Write-Summary($Results, [bool]$SkipWebFlag, [double]$TotalSeconds) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor White
    Write-Host "QUALITY GATE SUMMARY" -ForegroundColor White
    Write-Host "------------------------------------------------------------" -ForegroundColor White

    $passedCount = 0
    $failedCount = 0
    $skippedCount = 0

    foreach ($r in $Results) {
        $statusStr = "PASS"
        $color = "Green"
        if ($r.Skipped) {
            $statusStr = "SKIP"
            $color = "Yellow"
            $skippedCount++
        } elseif (-not $r.Passed) {
            $statusStr = "FAIL"
            $color = "Red"
            $failedCount++
        } else {
            $passedCount++
        }

        $line = "{0,-18} {1,-8} {2,8:N1}s" -f $r.Name, $statusStr, $r.Duration
        Write-Host $line -ForegroundColor $color
    }

    Write-Host "------------------------------------------------------------" -ForegroundColor White
    $totalSteps = @($Results).Count
    if ($failedCount -gt 0) {
        Write-Host ("RESULT: FAIL ({0}/{1} failed) in {2:N1}s" -f $failedCount, $totalSteps, $TotalSeconds) -ForegroundColor Red
        return 1
    } elseif ($SkipWebFlag) {
        Write-Host ("RESULT: PARTIAL ({0}/{1} passed, {2} skipped) in {3:N1}s [NOT valid for DoD]" -f $passedCount, $totalSteps, $skippedCount, $TotalSeconds) -ForegroundColor Yellow
        return 0
    } else {
        Write-Host ("RESULT: PASS ({0}/{1}) in {2:N1}s" -f $passedCount, $totalSteps, $TotalSeconds) -ForegroundColor Green
        return 0
    }
}

# --- Main Entry Point ---

$taijiRoot = Resolve-TaijiRoot $Root
$steps = Get-Steps $NoGpu $SkipWeb
$totalSteps = @($steps).Count

if ($DryRun) {
    Write-StepPlan $steps
    exit 0
}

# Recursion check. It needs no environment, so it runs before preflight (BUG-0010): a nested run is refused
# immediately, and a test can reach this branch without starting any step.
if ($env:TAIJI_CHECK_RUNNING -eq '1') {
    Write-Host "nested gate run refused: TAIJI_CHECK_RUNNING is already set" -ForegroundColor Red
    exit 2
}

# Preflight check
$preflightErrors = @(Test-Preflight $taijiRoot $SkipWeb)
if ($preflightErrors.Count -gt 0) {
    Write-Host "PREFLIGHT ERROR(S):" -ForegroundColor Red
    foreach ($err in $preflightErrors) {
        Write-Host ("  - {0}" -f $err) -ForegroundColor Red
    }
    exit 2
}

$gateStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$results = @()
$env:TAIJI_CHECK_RUNNING = '1'

try {
    # Print environment header
    $gitProc = Invoke-SilentProcess 'git' ("-C `"{0}`" rev-parse --short HEAD" -f $taijiRoot)
    $gitShort = $gitProc.StdOut.Trim()
    $gitDirtyProc = Invoke-SilentProcess 'git' ("-C `"{0}`" status --porcelain" -f $taijiRoot)
    $dirtyStr = if ([string]::IsNullOrWhiteSpace($gitDirtyProc.StdOut)) { "clean" } else { "dirty" }
    $psVer = $PSVersionTable.PSVersion.ToString()

    $uvLauncher = Get-UvLauncher
    $pyVer = Get-ToolVersion (Join-Path $taijiRoot '.venv\Scripts\python.exe') '--version'
    $uvVer = Get-ToolVersion $uvLauncher.Exe ((@($uvLauncher.Prefix) + @('--version')) -join ' ')
    if ($SkipWeb) {
        $nodeVer = 'skipped (-SkipWeb)'
        $pnpmVer = 'skipped (-SkipWeb)'
    } else {
        $nodeVer = Get-ToolVersion 'node' '--version'
        # pnpm.cmd is a shim that locates its files through %~dp0, which is empty for a bare name: pass the full path.
        $pnpmVer = Get-ToolVersion (Get-Command 'pnpm.cmd').Source '--version'
    }

    Write-Host "Taiji AI Quality Gate (P0.05)" -ForegroundColor Cyan
    Write-Host ("PowerShell: {0} | Git: {1} ({2}) | Flags: NoGpu={3}, SkipWeb={4}" -f $psVer, $gitShort, $dirtyStr, [bool]$NoGpu, [bool]$SkipWeb) -ForegroundColor Gray
    Write-Host ("Python: {0} | uv: {1} | Node: {2} | pnpm: {3}" -f $pyVer, $uvVer, $nodeVer, $pnpmVer) -ForegroundColor Gray
    Write-Host ""

    foreach ($step in $steps) {
        if ($step.SkipReason -ne '') {
            Write-Host ("==> [{0}/{1}] {2} - SKIPPED ({3})" -f $step.Number, $totalSteps, $step.Name, $step.SkipReason) -ForegroundColor Yellow
            $results += [pscustomobject]@{
                Name     = $step.Name
                Passed   = $true
                Duration = 0.0
                Skipped  = $true
            }
        } else {
            $res = Invoke-Step $step $taijiRoot $totalSteps
            $results += $res
        }
    }
} finally {
    Remove-Item Env:\TAIJI_CHECK_RUNNING -ErrorAction SilentlyContinue
    $gateStopwatch.Stop()
}

$finalExit = Write-Summary $results $SkipWeb $gateStopwatch.Elapsed.TotalSeconds
exit $finalExit
