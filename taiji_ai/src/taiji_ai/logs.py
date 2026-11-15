"""Unified logging: one root handler, a log file per run, absolute-path redaction (task P0.06).

Line format (console and ``run.log``)::

    2026-11-15T10:22:03.123+07:00 INFO     taiji_ai.pose.runner [run=3f2a9c01b7de] pose done in 41.2 s

ISO-8601 local time with UTC offset and milliseconds, level padded to 8, logger name, the first 12 characters of the
active ``run_id`` (``-`` outside a run), message. The full ``run_id`` is written once, in the run's start line.

Redaction (``PathRedactor``) runs on the whole formatted text, tracebacks and captured warnings included:

- ``<data>``, ``<models>``, ``<web>``, ``<project>``, ``<venv>``, ``<python>`` replace ``Settings.data_dir``,
  ``models_dir``, ``web_dist_dir``, ``config.PROJECT_ROOT``, ``sys.prefix``, ``sys.base_prefix``; the relative tail
  is kept (``<data>\\runs\\<id>\\pose_raw.npz``). The longest root wins. A root that is a drive/filesystem anchor,
  or equal to or above the home or temp folder, is ignored (its tail could expose a profile).
- ``<path>`` replaces every other absolute path whole: drive (``C:\\``, ``C:/``), device / long-path (``\\\\?\\``,
  ``\\\\.\\``), UNC (``\\\\server\\share``), each also in the doubled-backslash ``repr()`` spelling; with POSIX path
  syntax on, the personal prefixes ``/home/``, ``/Users/``, ``/root/``, ``/tmp/``, ``/var/folders/``, ``/private/``,
  ``/mnt/``, ``/media/``, ``/Volumes/``, ``/run/user/``.
- Where a path ends: after a quote, at the matching closing quote (``'`` closes only when no letter or digit
  follows it, so ``O'Neil`` stays inside the path). An unquoted unknown path cannot be delimited (folder names contain
  spaces), so it is redacted to the end of the line: over-redaction is preferred to a leak. An unquoted known-root
  path ends at the first whitespace, and the rest of the line is scanned again.
- POSIX path syntax defaults to on for POSIX and off on Windows, where ``/home/x`` or ``/media/x`` can only be a URL
  path (``GET /media/x``). With it on, such request lines are redacted (documented limit).
- Not detectable: relative file names and free text that contain a name. Hence rule 2 below.

Threads: the run id lives in a context variable. A thread started without ``contextvars.copy_context().run`` logs
with ``run=-``, and its lines do not reach ``run.log``.

Rules (AGENTS.md §5.9, §6):

1. Library code: ``log = logging.getLogger(__name__)``; never ``print``, never ``basicConfig``, never add handlers.
2. Log IDs: ``run_id``, ``recording_id``, ``segment_id``/revision, participant **pseudonym**, ``take_id``, SHA-256
   prefix. Never log user-supplied file names or paths, never free text typed by a person (notes, labels), never
   frame data.
3. Paths inside our folders are fine (redacted to ``<data>\\...``); still prefer IDs.
4. No per-frame INFO lines. Progress: at most one line every few seconds.
5. Exceptions: ``log.exception(...)`` in the handler that decides what happens next; do not log and re-raise the same
   error at every level.
6. The API never returns exception text to a client unless it went through ``PathRedactor`` (error codes preferred,
   T-API-02).
"""

from __future__ import annotations

import contextvars
import logging
import os
import re
import sys
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Final, TextIO

from taiji_ai import __version__
from taiji_ai.config import PROJECT_ROOT, Settings, get_settings

RUN_LOG_NAME: Final = "run.log"
NO_RUN: Final = "-"
REDACTED: Final = "<path>"
LOG_FORMAT: Final = "%(asctime)s %(levelname)-8s %(name)s [run=%(run_id).12s] %(message)s"
LOG_LEVELS: Final = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

_TAIJI_HANDLER_ATTR: Final = "_taiji_logging_handler"
_RUN_ID_VAR: contextvars.ContextVar[str | None] = contextvars.ContextVar("TAIJI_RUN_ID", default=None)
_RUN_ID_RE: Final = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_QUOTES: Final = "'\""
# Characters that cannot occur in a Windows path, plus line ends: no path span ever crosses them.
_PATH_STOP: Final = frozenset('\r\n"<>|*?')
# A known root must end here, so that ``...\data2`` is not ``<data>`` + ``2``.
_ROOT_BOUNDARY: Final = r"(?=[\\/\s'\"<>|,;:)\]]|$)"
_WINDOWS_STARTS: Final = (
    r"(?<![\\\w])\\\\(?:\\\\)?[?.](?:\\\\|\\)",  # device / long-path prefix \\?\ or \\.\ (also repr-doubled)
    r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]",  # drive C:\ or C:/ (not http:// or 12:30)
    r"(?<![\\\w])\\\\(?:\\\\)?(?=[^\\/\s'\"<>|*?])",  # UNC \\server (also repr-doubled \\\\server)
)
_POSIX_START: Final = r"(?<![\w.~/:-])/(?:home|Users|root|tmp|var/folders|private|mnt|media|Volumes|run/user)/"
_CASE_INSENSITIVE_PATHS: Final = sys.platform == "win32"


def _closes(text: str, i: int, quote: str | None) -> bool:
    """True if ``text[i]`` is the quote that closes a path opened by ``quote``."""
    if quote is None or text[i] != quote:
        return False
    if quote == '"':
        return True
    nxt = text[i + 1] if i + 1 < len(text) else ""
    return not (nxt.isalnum() or nxt == "_")  # O'Neil: the apostrophe is part of the path


def _unknown_path_end(text: str, i: int, quote: str | None) -> int:
    """End of an unknown absolute path starting before ``i``: closing quote, a stop character, or end of text."""
    while i < len(text):
        if text[i] in _PATH_STOP or _closes(text, i, quote):
            return i
        i += 1
    return i


def _root_tail_end(text: str, i: int, quote: str | None) -> int:
    """End of the tail after a known root: like an unknown path when quoted, else also at whitespace or a quote."""
    if quote is not None:
        return _unknown_path_end(text, i, quote)
    while i < len(text):
        c = text[i]
        if c in _PATH_STOP or c in _QUOTES or c.isspace():
            return i
        i += 1
    return i


class PathRedactor:
    """Replace absolute filesystem paths in text (log lines, tracebacks, error strings shown to a client).

    Known roots keep their relative tail; every other absolute path becomes ``<path>``. See the module docstring
    for the exact rules and limits. ``posix_paths`` turns recognition of POSIX personal prefixes on or off
    (default: on for POSIX, off on Windows).
    """

    def __init__(self, roots: Mapping[str, str | os.PathLike[str]], *, posix_paths: bool | None = None) -> None:
        self._labels: dict[str, str] = {}
        for label, path in roots.items():
            placeholder = label if label.startswith("<") and label.endswith(">") else f"<{label}>"
            p = Path(path)
            if self._is_unsafe_root(p):
                continue
            for spelling in {str(p.resolve()), str(p.absolute())}:
                for variant in self._spellings(spelling):
                    self._labels.setdefault(self._norm(variant), placeholder)

        variants = sorted(self._labels, key=len, reverse=True)  # longest root first
        root_alt = "|".join(re.escape(v) for v in variants) or r"(?!)"
        starts = list(_WINDOWS_STARTS)
        if posix_paths if posix_paths is not None else os.name != "nt":
            starts.append(_POSIX_START)
        flags = re.IGNORECASE if _CASE_INSENSITIVE_PATHS else 0
        # Root alternatives come first: at the same position a known root wins over a generic path start.
        self._start_re = re.compile(
            rf"(?P<root>(?<![\w\\])(?:{root_alt})){_ROOT_BOUNDARY}|(?P<other>{'|'.join(starts)})", flags
        )

    @staticmethod
    def _spellings(path_str: str) -> list[str]:
        """The spellings a root takes in text: as is, with ``/``, and repr-doubled backslashes."""
        out = [path_str]
        if "\\" in path_str:
            out += [path_str.replace("\\", "/"), path_str.replace("\\", "\\\\")]
        return out

    @staticmethod
    def _norm(text: str) -> str:
        return text.casefold() if _CASE_INSENSITIVE_PATHS else text

    @staticmethod
    def _is_unsafe_root(path: Path) -> bool:
        """True when keeping tails below ``path`` could expose a profile: a filesystem anchor, the home or temp folder,
        or an ancestor of either. Fails closed: when the check cannot be done, the root is not used."""
        try:
            resolved = path.resolve()
            home = Path.home().resolve()
            temp_dir = Path(tempfile.gettempdir()).resolve()
        except (OSError, RuntimeError):  # unresolvable path, no home folder, no temp folder -> do not trust the root
            return True
        if resolved == Path(resolved.anchor):
            return True
        return any(guard == resolved or guard.is_relative_to(resolved) for guard in (home, temp_dir))

    @classmethod
    def for_settings(cls, settings: Settings, *, posix_paths: bool | None = None) -> PathRedactor:
        roots: dict[str, str | os.PathLike[str]] = {
            "<data>": settings.data_dir,
            "<models>": settings.models_dir,
            "<web>": settings.web_dist_dir,
            "<project>": PROJECT_ROOT,
            "<venv>": sys.prefix,
            "<python>": sys.base_prefix,
        }
        return cls(roots, posix_paths=posix_paths)

    def redact(self, text: str) -> str:
        """Return ``text`` with every absolute path replaced (one left-to-right pass; spans are never rescanned)."""
        if not text:
            return text
        out: list[str] = []
        pos = 0
        while (m := self._start_re.search(text, pos)) is not None:
            start = m.start()
            quote = text[start - 1] if start > 0 and text[start - 1] in _QUOTES else None
            out.append(text[pos:start])
            root = m.group("root")
            if root is not None:
                end = _root_tail_end(text, m.end("root"), quote)
                out.append(self._labels[self._norm(root)])
                out.append(text[m.end("root") : end])
            else:
                end = _unknown_path_end(text, m.end(), quote)
                out.append(REDACTED)
            pos = end
        out.append(text[pos:])
        return "".join(out)


class RunContextFilter(logging.Filter):
    """Sets ``record.run_id`` from the current context (``-`` outside a run) unless a filter already did."""

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "run_id", None) is None:
            cid = _RUN_ID_VAR.get()
            record.run_id = cid if cid is not None else NO_RUN
        return True


class RunMatchFilter(logging.Filter):
    """Passes only records whose ``run_id`` equals the given run's id."""

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        return getattr(record, "run_id", None) == self.run_id


class RedactingFormatter(logging.Formatter):
    """ISO-8601 timestamps with UTC offset; the whole formatted text (traceback included) goes through the redactor."""

    def __init__(self, redactor: PathRedactor, fmt: str | None = None, datefmt: str | None = None) -> None:
        super().__init__(fmt=fmt or LOG_FORMAT, datefmt=datefmt)
        self.redactor = redactor

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        return datetime.fromtimestamp(record.created).astimezone().isoformat(timespec="milliseconds")

    def format(self, record: logging.LogRecord) -> str:
        if getattr(record, "run_id", None) is None:
            record.run_id = NO_RUN
        return self.redactor.redact(super().format(record))


def _level_number(level: str | int) -> int:
    if isinstance(level, int) and not isinstance(level, bool):
        return level
    name = level.strip().upper() if isinstance(level, str) else ""
    if name not in LOG_LEVELS:
        raise ValueError(f"TAIJI_LOG_LEVEL must be one of {', '.join(LOG_LEVELS)}; got {level!r}")
    return logging.getLevelNamesMapping()[name]


def configure_logging(
    settings: Settings | None = None,
    *,
    level: str | int | None = None,
    stream: TextIO | None = None,
) -> logging.Handler:
    """Install the one console handler of the process on the root logger (idempotent) and return it.

    Level: ``level`` if given, else ``settings.log_level`` (``TAIJI_LOG_LEVEL``); one of ``LOG_LEVELS`` or an int,
    otherwise ``ValueError``. Replaces only a handler installed by an earlier call; other handlers stay. Routes
    ``warnings`` through logging. Call it from entry points only (``python -m taiji_ai.api``, the worker).
    """
    settings = settings or get_settings()
    int_level = _level_number(level if level is not None else settings.log_level)

    root = logging.getLogger()
    for h in [h for h in root.handlers if getattr(h, _TAIJI_HANDLER_ATTR, False)]:
        root.removeHandler(h)
        h.close()

    handler = logging.StreamHandler(stream or sys.stderr)
    setattr(handler, _TAIJI_HANDLER_ATTR, True)
    handler.setFormatter(RedactingFormatter(PathRedactor.for_settings(settings)))
    handler.addFilter(RunContextFilter())

    root.addHandler(handler)
    root.setLevel(int_level)
    logging.captureWarnings(True)
    return handler


@contextmanager
def run_log(
    run_dir: str | os.PathLike[str],
    run_id: str,
    settings: Settings | None = None,
) -> Iterator[Path]:
    """Write every record of this run (same context) to ``<run_dir>/run.log`` while the block runs; yield the path.

    Appends (a resumed run adds a new ``run log start`` block). Ends with ``run log end: ok`` or
    ``run log end: <ExceptionType>`` — also for ``KeyboardInterrupt``/``SystemExit`` — and re-raises. Requires
    ``configure_logging()`` first; refuses nesting and run ids outside ``[A-Za-z0-9_-]{1,64}``. ``run.log`` is a
    diagnostic file, not an artifact: not written atomically, not in manifest checksums or the cache key (DEC-0012).
    """
    if not isinstance(run_id, str) or not _RUN_ID_RE.match(run_id):
        raise ValueError(f"Invalid run_id {run_id!r}: must match ^[A-Za-z0-9_-]{{1,64}}$")
    active = current_run_id()
    if active is not None:
        raise RuntimeError(f"run_log() is already active for run {active}")
    root = logging.getLogger()
    if not any(getattr(h, _TAIJI_HANDLER_ATTR, False) for h in root.handlers):
        raise RuntimeError("call taiji_ai.logs.configure_logging() first")

    settings = settings or get_settings()
    run_dir_path = Path(run_dir).resolve()
    run_dir_path.mkdir(parents=True, exist_ok=True)
    log_file = run_dir_path / RUN_LOG_NAME

    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setFormatter(RedactingFormatter(PathRedactor.for_settings(settings)))
    # Own context filter: after a re-configuration this handler is first in line and must set run_id itself.
    file_handler.addFilter(RunContextFilter())
    file_handler.addFilter(RunMatchFilter(run_id))

    root.addHandler(file_handler)
    token = _RUN_ID_VAR.set(run_id)
    log = logging.getLogger(__name__)
    log.info("run log start: run_id=%s taiji_ai=%s pid=%d", run_id, __version__, os.getpid())
    try:
        yield log_file
        log.info("run log end: ok")
    except BaseException as exc:  # also cancellation (KeyboardInterrupt, SystemExit): record it, then re-raise
        log.error("run log end: %s", type(exc).__name__)
        raise
    finally:
        root.removeHandler(file_handler)
        file_handler.close()
        _RUN_ID_VAR.reset(token)


def current_run_id() -> str | None:
    """The run id active in the current context, or ``None``."""
    return _RUN_ID_VAR.get()
