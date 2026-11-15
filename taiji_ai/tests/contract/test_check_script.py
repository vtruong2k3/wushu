from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from taiji_ai.config import PROJECT_ROOT

CHECK_SCRIPT = PROJECT_ROOT / "tools" / "check.ps1"
GUARD_VAR = "TAIJI_CHECK_RUNNING"
powershell_available = shutil.which("powershell") is not None

# Parses the script named by $env:TAIJI_PARSE_TARGET (no quoting problems with the path) and prints one
# "ParseError: <id>: <message>" line per syntax error. Exit 1 when there is at least one error, else 0.
# Parser::ParseFile reports errors only through its third (out) argument, so it must be captured, not [ref]$null.
PARSE_CMD = (
    "$tokens = $null; $errors = $null; "
    "[void][System.Management.Automation.Language.Parser]::ParseFile("
    "$env:TAIJI_PARSE_TARGET, [ref]$tokens, [ref]$errors); "
    "foreach ($e in $errors) { Write-Output ('ParseError: {0}: {1}' -f $e.ErrorId, $e.Message) }; "
    "if ($errors.Count -gt 0) { exit 1 }; exit 0"
)


def parse_errors(script: Path) -> subprocess.CompletedProcess[str]:
    """Parse `script` with the Windows PowerShell parser; stdout lists the syntax errors."""
    env = os.environ.copy()
    env["TAIJI_PARSE_TARGET"] = str(script.resolve())
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", PARSE_CMD],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=env,
        timeout=60,
    )


def run_powershell(
    args: list[str],
    cwd: Path | None = None,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run tools/check.ps1 with `args`. Tests must never start a real gate run (plan risk R5)."""
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(CHECK_SCRIPT), *args]
    env = os.environ.copy()
    # The gate sets the guard variable while pytest runs inside it. Only the guard test may set it on purpose.
    env.pop(GUARD_VAR, None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        cmd,
        cwd=cwd or PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=env,
        timeout=180,  # safety net: a runaway nested gate must fail the test, not hang the machine
    )


def test_t_tool_01_check_script_is_ascii_only():
    content = CHECK_SCRIPT.read_bytes()
    assert content.isascii(), "tools/check.ps1 must be ASCII-only for PowerShell 5.1 compatibility"


@pytest.mark.skipif(not powershell_available, reason="powershell required")
def test_t_tool_01_check_script_parses_cleanly_in_powershell():
    res = parse_errors(CHECK_SCRIPT)
    assert res.returncode == 0, f"Parse errors in check.ps1: {res.stdout} {res.stderr}"
    assert res.stdout.strip() == ""
    assert res.stderr.strip() == ""


@pytest.mark.skipif(not powershell_available, reason="powershell required")
def test_t_tool_01_parse_check_detects_syntax_errors(tmp_path: Path):
    """Negative control (BUG-0008): the same helper must fail on a broken script."""
    bad_script = tmp_path / "bad_syntax.ps1"
    bad_script.write_text('function Foo {\n    if ($x -eq 1 {\n        "unclosed"\n}\n', encoding="ascii")
    res = parse_errors(bad_script)
    assert res.returncode == 1, f"parse check must fail on a syntax error: {res.stdout} {res.stderr}"
    assert "ParseError:" in res.stdout


@pytest.mark.skipif(not powershell_available, reason="powershell required")
def test_t_tool_02_dryrun_prints_all_10_steps_in_order():
    res = run_powershell(["-DryRun"])
    assert res.returncode == 0, f"DryRun failed with stderr: {res.stderr}"
    lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]

    assert len(lines) == 10, f"Expected 10 lines, got {len(lines)}: {lines}"

    expected_steps = [
        ("uv-lock", ".", ["uv lock --check", "py -3.12 -m uv lock --check"]),
        ("ruff-check", ".", [".venv\\Scripts\\python.exe -m ruff check src tests tools"]),
        ("ruff-format", ".", [".venv\\Scripts\\python.exe -m ruff format --check src tests tools"]),
        ("mypy", ".", [".venv\\Scripts\\python.exe -m mypy src"]),
        ("pytest", ".", [".venv\\Scripts\\python.exe -m pytest -rs"]),
        ("web-lint", "web", ["pnpm.cmd lint"]),
        ("web-typecheck", "web", ["pnpm.cmd typecheck"]),
        ("web-test", "web", ["pnpm.cmd test"]),
        ("web-build", "web", ["pnpm.cmd build"]),
        ("repo-hygiene", ".", [".venv\\Scripts\\python.exe tools\\repo_hygiene.py"]),
    ]

    for idx, (line, (exp_name, exp_dir, exp_cmd_options)) in enumerate(
        zip(lines, expected_steps, strict=True), start=1
    ):
        parts = line.split("|")
        assert len(parts) == 5, f"Line {idx} expected 5 fields separated by '|', got: {line}"
        assert parts[0] == "STEP"
        assert int(parts[1]) == idx
        assert parts[2] == exp_name
        assert parts[3] == exp_dir
        cmd = parts[4].strip()
        assert cmd in exp_cmd_options, (
            f"Step {idx} ({exp_name}): command '{cmd}' did not match any expected option: {exp_cmd_options}"
        )
        # plan section 2.1: paths are relative to taiji_ai/, never an absolute (personal) path
        assert re.search(r"[A-Za-z]:\\", line) is None, f"Step {idx} prints an absolute path: {line}"

    # Step 5 pytest has -rs and does not have 'not gpu'
    pytest_line = lines[4]
    assert "-rs" in pytest_line
    assert "not gpu" not in pytest_line


@pytest.mark.skipif(not powershell_available, reason="powershell required")
def test_t_tool_03_nogpu_flag_deselects_gpu_tests():
    res = run_powershell(["-DryRun", "-NoGpu"])
    assert res.returncode == 0
    pytest_line = [line for line in res.stdout.splitlines() if "pytest" in line][0]
    assert "not gpu" in pytest_line


@pytest.mark.skipif(not powershell_available, reason="powershell required")
def test_t_tool_03_skipweb_flag_skips_four_web_steps():
    res = run_powershell(["-DryRun", "-SkipWeb"])
    assert res.returncode == 0
    skip_lines = [line for line in res.stdout.splitlines() if line.startswith("SKIP")]
    assert len(skip_lines) == 4
    for line in skip_lines:
        assert "skipped via -SkipWeb" in line


@pytest.mark.skipif(not powershell_available, reason="powershell required")
def test_t_tool_03_preflight_error_exits_2_without_running_a_step(tmp_path: Path):
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    res = run_powershell(["-Root", str(empty_dir)])
    out = res.stdout + res.stderr
    assert res.returncode == 2
    assert "uv sync" in out
    assert "==>" not in out, "no step may start when preflight fails"


@pytest.mark.skipif(not powershell_available, reason="powershell required")
def test_bug_0010_nested_guard_is_checked_before_preflight(tmp_path: Path):
    """BUG-0010: the nested-run guard needs no environment, so it must answer before preflight.

    The empty -Root makes preflight fail. If the guard were broken, preflight would be the only barrier and
    this test would see the preflight message instead of the refusal. No gate run is ever started.
    """
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    res = run_powershell(["-Root", str(empty_dir)], env_extra={GUARD_VAR: "1"})
    out = res.stdout + res.stderr
    assert res.returncode == 2
    assert "nested gate run refused" in out
    assert "uv sync" not in out, "preflight ran before the guard"
    assert "==>" not in out, "no step may start in a nested run"


@pytest.mark.skipif(not powershell_available, reason="powershell required")
def test_t_tool_03_dryrun_ignores_nested_guard():
    """-DryRun is pure (plan section 2.1): it works even inside a gate run, where the guard variable is set."""
    res = run_powershell(["-DryRun"], env_extra={GUARD_VAR: "1"})
    assert res.returncode == 0
    assert len([line for line in res.stdout.splitlines() if line.startswith("STEP")]) == 10
