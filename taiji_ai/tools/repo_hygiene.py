"""Repository hygiene gate (AGENTS.md 5.9, 8, 9.4.8): fail if git would track data, media, model weights,
dataset or third-party clone contents, secrets, or oversized files. Used by tools/check.ps1 (task P0.05).

Exit codes: 0 clean, 1 violations found, 2 the check could not be completed (git failed, or a listed file
could not be stat'ed). A file that cannot be checked is never treated as clean (BUG-0009).
"""

from __future__ import annotations

import argparse
import re
import stat
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

DEFAULT_MAX_MB: float = 5.0

MEDIA_EXTS = frozenset({".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm", ".wav", ".mp3", ".flac", ".m4a", ".aac"})
MODEL_EXTS = frozenset({".onnx", ".pt", ".pth", ".ckpt", ".safetensors", ".engine", ".trt"})
ARCHIVE_EXTS = frozenset({".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz"})
ARRAY_EXTS = frozenset({".npz", ".npy", ".parquet", ".h5", ".hdf5", ".feather", ".pkl", ".pickle"})
DB_EXTS = frozenset({".sqlite", ".sqlite3", ".db"})
DB_COMPANION_SUFFIXES = ("-wal", "-shm", "-journal")

SECRET_EXTS = frozenset({".pem", ".key", ".pfx", ".p12"})
SECRET_EXACT_NAMES = frozenset({"id_rsa", "id_ed25519"})


@dataclass(frozen=True)
class Violation:
    path: str  # repo-relative, forward slashes
    rule: str  # rule id + short reason, e.g. "R1 media file (.webm)"


def normalize_repo_relpath(path: str | Path) -> str:
    s = str(path).replace("\\", "/").strip()
    while s.startswith("./"):
        s = s[2:]
    return s.lstrip("/")


def classify(path: str | Path, size_bytes: int | None, max_bytes: int) -> list[str]:
    rel = normalize_repo_relpath(path)
    if not rel:
        return []

    posix = PurePosixPath(rel)
    name = posix.name
    lower_name = name.lower()
    lower_suffix = posix.suffix.lower()
    violations: list[str] = []

    # R1: media
    if lower_suffix in MEDIA_EXTS:
        violations.append(f"R1 media file ({lower_suffix})")

    # R2: model weights
    if lower_suffix in MODEL_EXTS:
        violations.append(f"R2 model weights ({lower_suffix})")

    # R3: archives
    # check multi-suffix like .tar.gz
    full_suffixes = "".join(posix.suffixes).lower()
    if lower_suffix in ARCHIVE_EXTS or any(full_suffixes.endswith(ext) for ext in ARCHIVE_EXTS):
        violations.append(f"R3 archive ({lower_suffix})")

    # R4: arrays / pickles
    if lower_suffix in ARRAY_EXTS:
        violations.append(f"R4 array or pickle ({lower_suffix})")

    # R5: databases
    if lower_suffix in DB_EXTS or any(lower_name.endswith(comp) for comp in DB_COMPANION_SUFFIXES):
        violations.append(f"R5 database file ({name})")

    # R6: dataset contents (allowed: datasets/<area>/README.md)
    parts = posix.parts
    if len(parts) >= 1 and parts[0].lower() == "datasets":
        is_allowed = len(parts) == 3 and parts[2].lower() == "readme.md"
        if not is_allowed:
            violations.append("R6 dataset content (datasets/*/* forbidden except datasets/<area>/README.md)")

    # R7: third-party clones (allowed: repos/<area>/REPOS.md)
    if len(parts) >= 1 and parts[0].lower() == "repos":
        is_allowed = len(parts) == 3 and parts[2].lower() == "repos.md"
        if not is_allowed:
            violations.append("R7 third-party repository clone (repos/*/* forbidden except repos/<area>/REPOS.md)")

    # R8: vendored / build output
    lower_parts = [p.lower() for p in parts]
    if (
        "node_modules" in lower_parts
        or ".venv" in lower_parts
        or "__pycache__" in lower_parts
        or rel.lower().startswith("taiji_ai/web/dist/")
    ):
        violations.append("R8 build output or vendored dependency directory")

    # R9: runtime data / models dirs
    if rel.lower().startswith("taiji_ai/data/"):
        if rel != "taiji_ai/data/.gitkeep":
            violations.append("R9 runtime data file (taiji_ai/data/* forbidden except .gitkeep)")
    elif rel.lower().startswith("taiji_ai/models/"):
        allowed_models = {"taiji_ai/models/.gitkeep", "taiji_ai/models/registry.json"}
        if rel not in allowed_models:
            violations.append("R9 runtime models file (taiji_ai/models/* forbidden except .gitkeep and registry.json)")

    # R10: secrets
    if lower_name == ".env" or (
        lower_name.startswith(".env.") and not re.match(r"^\.env\.(example|sample)$", lower_name)
    ):
        violations.append(f"R10 environment / secret file ({name})")
    elif lower_suffix in SECRET_EXTS:
        violations.append(f"R10 secret key / certificate ({lower_suffix})")
    elif lower_name in SECRET_EXACT_NAMES:
        violations.append(f"R10 private key ({name})")

    # R11: size limit
    if size_bytes is not None and size_bytes > max_bytes:
        mb = size_bytes / (1024 * 1024)
        max_mb = max_bytes / (1024 * 1024)
        violations.append(f"R11 file size {mb:.2f} MB exceeds limit {max_mb:.2f} MB")

    return violations


def find_violations(entries: Iterable[tuple[str, int | None]], max_bytes: int) -> list[Violation]:
    out: list[Violation] = []
    for path, size_bytes in entries:
        rules = classify(path, size_bytes, max_bytes)
        norm_path = normalize_repo_relpath(path)
        for r in rules:
            out.append(Violation(path=norm_path, rule=r))
    return out


def list_candidate_files(repo_root: Path) -> list[str]:
    """git ls-files -z --cached --others --exclude-standard (tracked + untracked-not-ignored)."""
    cmd = ["git", "-C", str(repo_root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False)
    except FileNotFoundError as err:
        raise RuntimeError("git executable not found on PATH") from err

    if proc.returncode != 0:
        err_msg = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git ls-files failed (exit {proc.returncode}): {err_msg}")

    try:
        raw = proc.stdout.decode("utf-8")
    except UnicodeDecodeError as err:
        raise RuntimeError(f"Failed to decode git output as UTF-8: {err}") from err

    if not raw:
        return []
    items = raw.split("\0")
    return [it for it in items if it]


def find_repo_root(start_dir: Path | None = None) -> Path:
    curr = (start_dir or Path.cwd()).resolve()
    for parent in [curr, *curr.parents]:
        if (parent / ".git").exists():
            return parent
    return curr


def collect_entries(
    repo_root: Path, files: Iterable[str]
) -> tuple[list[tuple[str, int | None]], list[tuple[str, str]]]:
    """Return ``(entries, stat_errors)`` for repo-relative `files`.

    ``entries`` holds ``(path, size_bytes)``; the size is ``None`` only when the file is listed by git but
    missing on disk (deleted from the working tree, still indexed), and ``0`` for a directory or other
    non-regular entry (for example a submodule). ``stat_errors`` holds ``(path, reason)`` for every file that
    exists but could not be stat'ed; those files are not in ``entries`` because their size is unknown.
    """
    entries: list[tuple[str, int | None]] = []
    stat_errors: list[tuple[str, str]] = []
    for rel in files:
        try:
            st = (repo_root / rel).stat()
        except (FileNotFoundError, NotADirectoryError):
            entries.append((rel, None))
        except OSError as err:
            stat_errors.append((rel, str(err)))
        else:
            entries.append((rel, st.st_size if stat.S_ISREG(st.st_mode) else 0))
    return entries, stat_errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Repository hygiene checker (P0.05). Exit 0 clean, 1 violations, "
        "2 git error or a file that cannot be stat'ed."
    )
    parser.add_argument("--repo-root", type=Path, default=None, help="Root of git repository")
    parser.add_argument(
        "--max-mb",
        type=float,
        default=DEFAULT_MAX_MB,
        help=f"Maximum allowed file size in MB (default: {DEFAULT_MAX_MB})",
    )
    args = parser.parse_args(argv)

    try:
        repo_root = args.repo_root.resolve() if args.repo_root else find_repo_root()
        files = list_candidate_files(repo_root)
    except (RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    max_bytes = int(args.max_mb * 1024 * 1024)
    entries, stat_errors = collect_entries(repo_root, files)
    violations = find_violations(entries, max_bytes)

    if violations:
        print(f"Repository hygiene violations found ({len(violations)}):", file=sys.stderr)
        for v in violations:
            print(f"  {v.path}: {v.rule}", file=sys.stderr)

    if stat_errors:
        # The verdict is unknown for these files: report each one and never return 0 or 1.
        for rel, reason in stat_errors:
            print(f"Error: cannot stat {rel}: {reason}", file=sys.stderr)
        print(f"\nERROR: {len(stat_errors)} of {len(files)} files could not be checked.", file=sys.stderr)
        return 2

    if violations:
        print(f"\nFAIL: {len(violations)} violation(s) in {len(files)} files checked.", file=sys.stderr)
        return 1

    print(f"PASS: 0 violations, {len(files)} files checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
