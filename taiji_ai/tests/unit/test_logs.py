"""T-CORE-01: unified logging, per-run log file, absolute-path redaction (task P0.06).

All names are the synthetic placeholder ``Người Tập Giả``; every redaction test checks the input really contains it.
The ``clean_logging`` fixture lives in ``tests/conftest.py`` (BUG-0016).
"""

from __future__ import annotations

import contextvars
import io
import logging
import os
import re
import tempfile
import threading
import warnings
from pathlib import Path

import pytest

from taiji_ai.config import PROJECT_ROOT, Settings
from taiji_ai.logs import (
    RUN_LOG_NAME,
    PathRedactor,
    configure_logging,
    current_run_id,
    run_log,
)

FAKE_NAME = "Người Tập Giả"
# Any drive-letter or UNC path start left in an output means an absolute path survived.
ABS_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]|(?<![\\\w])\\\\[^\\\s]")


# --- T-CORE-01a: unknown absolute paths with the fake name are replaced whole by <path> ---
@pytest.mark.parametrize(
    "path_template",
    [
        r"C:\Users\{name}\Videos\routine.mp4",
        r"C:/Users/{name}/Videos/routine.mp4",
        r"c:\users\{name}\videos\routine.mp4",
        r"C:\\Users\\{name}\\Videos\\routine.mp4",
        r"\\nas\share\{name}\routine.mp4",
        r"\\nas\Video Share\{name}\routine.mp4",  # BUG-0014: space in the share name
        r"\\nas\Tài liệu\{name}\routine.mp4",  # BUG-0014: non-ASCII share name
        r"\\pc01\c$\Users\{name}\routine.mp4",  # BUG-0014: admin share
        r"\\máy-chủ\share\{name}\routine.mp4",  # BUG-0014: non-ASCII server name
        r"\\?\C:\Users\{name}\Videos\routine.mp4",
        r"\\?\UNC\nas\Video Share\{name}\routine.mp4",  # BUG-0014
        r"C:\Users\O'Neil\{name}\routine.mp4",  # BUG-0014: apostrophe inside a quoted path
    ],
)
def test_t_core_01a_absolute_paths_redacted_to_path(path_template: str):
    inp = f"error accessing '{path_template.format(name=FAKE_NAME)}'"
    assert FAKE_NAME in inp  # negative control

    redacted = PathRedactor({}).redact(inp)

    assert FAKE_NAME not in redacted
    assert redacted == "error accessing '<path>'"


@pytest.mark.parametrize(
    "path_template",
    [
        "\\\\nas\\Video Share\\{name}\\x.mp4",
        "C:\\Users\\O'Neil\\{name}\\x.mp4",  # repr() switches to double quotes
        "\\\\pc01\\c$\\Users\\{name}\\x.mp4",
        "\\\\?\\C:\\Users\\{name}\\x.mp4",
    ],
)
def test_t_core_01a_repr_forms_redacted(path_template: str):
    """BUG-0014: the doubled-backslash repr() spelling (what exception texts contain) is redacted whole."""
    inp = f"error: {path_template.format(name=FAKE_NAME)!r}"
    assert FAKE_NAME in inp
    quote = inp[len("error: ")]

    assert PathRedactor({}).redact(inp) == f"error: {quote}<path>{quote}"


@pytest.mark.parametrize(
    "path_template",
    [r"C:\Users\{name}\x.mp4", r"\\nas\Video Share\{name}\x.mp4", r"\\pc01\c$\Users\{name}\x.mp4"],
)
def test_t_core_01a_unquoted_path_redacted_to_end_of_line(path_template: str):
    """Without quotes the end of a path is unknown (names have spaces): redact to the end of the line only."""
    inp = f"cannot open {path_template.format(name=FAKE_NAME)} now\nnext line"
    assert FAKE_NAME in inp

    assert PathRedactor({}).redact(inp) == "cannot open <path>\nnext line"


@pytest.mark.parametrize(
    "path_template", ["/home/{name}/videos/x.mp4", "/Users/{name}/x.mp4", "/mnt/c/Users/{name}/x.mp4"]
)
def test_t_core_01a_posix_personal_paths_redacted(path_template: str):
    """POSIX personal prefixes are redacted when POSIX path syntax is on (default on POSIX, off on Windows)."""
    inp = f"open '{path_template.format(name=FAKE_NAME)}'"
    assert FAKE_NAME in inp

    assert PathRedactor({}, posix_paths=True).redact(inp) == "open '<path>'"


# --- T-CORE-01b: known roots keep the tail ---
def test_t_core_01b_known_roots_keep_tail(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path / "data",
        models_dir=tmp_path / "models",
        web_dist_dir=tmp_path / "web" / "dist",
    )
    redactor = PathRedactor.for_settings(settings)

    # 1. Data dir
    data_file = settings.data_dir / "runs" / "r1" / "pose_raw.npz"
    r1 = redactor.redact(f"wrote artifact {data_file}")
    assert r1 == r"wrote artifact <data>\runs\r1\pose_raw.npz" or r1 == "wrote artifact <data>/runs/r1/pose_raw.npz"

    # 2. Forward-slash spelling
    s2 = f"wrote {settings.data_dir.as_posix()}/runs/r1/pose_raw.npz"
    assert redactor.redact(s2) == "wrote <data>/runs/r1/pose_raw.npz"

    # 3. Project root
    src_file = PROJECT_ROOT / "src" / "taiji_ai" / "logs.py"
    r3 = redactor.redact(f"loaded {src_file}")
    assert r3 == f"loaded <project>{os.sep}src{os.sep}taiji_ai{os.sep}logs.py"

    # 4. Longest root wins: if data_dir is inside project_root, <data> wins over <project>
    inside_data = PROJECT_ROOT / "data" / "rec" / "pose.npz"
    redactor_proj = PathRedactor({"<project>": PROJECT_ROOT, "<data>": PROJECT_ROOT / "data"})
    assert redactor_proj.redact(str(inside_data)).startswith("<data>")


def test_t_core_01b_known_roots_keep_tail_in_repr_form(tmp_path: Path):
    """BUG-0015: the repr() spelling keeps the tail too (FileNotFoundError texts use it)."""
    settings = Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models", web_dist_dir=tmp_path / "dist")
    redactor = PathRedactor.for_settings(settings)
    data = settings.data_dir.resolve()
    escaped_root = repr(str(data))[1:-1]

    artifact = repr(str(data / "runs" / "r1" / "pose_raw.npz"))
    assert redactor.redact(artifact) == artifact.replace(escaped_root, "<data>")

    err = str(FileNotFoundError(2, "No such file", str(data / "runs" / "r1")))
    assert redactor.redact(err) == err.replace(escaped_root, "<data>")

    src = repr(str(PROJECT_ROOT / "src" / "taiji_ai" / "logs.py"))
    assert redactor.redact(src) == src.replace(repr(str(PROJECT_ROOT))[1:-1], "<project>")

    assert redactor.redact(f"{PROJECT_ROOT}/tmp/x.txt") == "<project>/tmp/x.txt"


def test_t_core_01b_tail_of_known_root_does_not_hide_a_second_path(tmp_path: Path):
    """An unquoted known-root path ends at whitespace, so a personal path later on the line is still redacted."""
    redactor = PathRedactor({"<data>": tmp_path / "data"})
    inp = f"moved {tmp_path / 'data' / 'x.npz'} from C:\\Users\\{FAKE_NAME}\\x.mp4"

    out = redactor.redact(inp)

    assert FAKE_NAME not in out
    assert out == f"moved <data>{os.sep}x.npz from <path>"


# --- T-CORE-01c: boundary check & over-redaction stops at quote / < ---
def test_t_core_01c_boundary_and_over_redaction_stopping(tmp_path: Path):
    redactor = PathRedactor({"<data>": tmp_path / "data"})

    # Boundary: data2 is NOT <data>
    other_folder = tmp_path / "data2" / "test.txt"
    r = redactor.redact(str(other_folder))
    assert "<data>2" not in r
    assert r == "<path>"

    # Over-redaction stops at the closing quote or <
    msg = f"file '{tmp_path / 'other' / 'bad.mp4'}' was not found; <info> next"
    assert redactor.redact(msg) == "file '<path>' was not found; <info> next"


# --- T-CORE-01d: unsafe roots ignored ---
def test_t_core_01d_unsafe_roots_ignored():
    anchor = Path(Path.cwd().anchor)
    home = Path.home()
    temp_dir = Path(tempfile.gettempdir())

    redactor = PathRedactor({"<root_drive>": anchor, "<home_root>": home, "<temp_root>": temp_dir})
    out = redactor.redact(str(home / FAKE_NAME / "secret.txt"))
    assert "<home_root>" not in out and "<root_drive>" not in out
    assert out == "<path>"


def test_t_core_01d_temp_folder_is_not_a_root():
    """A temp-folder root would keep everything below it (other users' files, uploads): it must be ignored."""
    temp_dir = Path(tempfile.gettempdir())
    redactor = PathRedactor({"<temp_root>": temp_dir})
    inp = str(temp_dir / FAKE_NAME / "upload.mp4")
    assert FAKE_NAME in inp

    out = redactor.redact(inp)

    assert FAKE_NAME not in out
    assert out == "<path>"


# --- T-CORE-01e: not paths, left unchanged ---
def test_t_core_01e_not_paths_left_unchanged():
    unchanged = [
        "http://127.0.0.1:8007/api/health",
        "https://example.com/api/v1/test",
        "/api/runs/abc",
        "10:22:03",
        "aspect ratio 3:2",
        "/homepage",  # BUG-0015
        "see /users list",  # BUG-0015
        "GET /media/x",  # BUG-0015
        "/private-notes",  # BUG-0015
    ]
    windows_syntax = PathRedactor({}, posix_paths=False)
    for text in unchanged:
        assert windows_syntax.redact(text) == text

    posix_syntax = PathRedactor({}, posix_paths=True)
    for text in ["http://127.0.0.1:8007/api/health", "/api/runs/abc", "/homepage", "see /users list", "/private-notes"]:
        assert posix_syntax.redact(text) == text
    # Documented limit: with POSIX syntax on, /media/<x> is a Linux mount point, so a request line for it is redacted.
    assert posix_syntax.redact("GET /media/x") == "GET <path>"

    # file:// keeps the scheme
    assert PathRedactor({}).redact(r"file:///C:/Users/test/file.mp4") == "file:///<path>"


def test_t_core_01e_posix_syntax_default_follows_the_platform(tmp_path: Path):
    """BUG-0019: POSIX personal prefixes are redacted by default only where POSIX path syntax is used.

    On Windows a request line such as ``GET /home/settings`` is a URL path and must stay readable; every explicit
    ``posix_paths=...`` test above would pass even if the default were wrong, so the default is checked here.
    """
    text = "GET /home/settings"
    expected = "GET <path>" if os.name != "nt" else text
    assert PathRedactor({}).redact(text) == expected
    settings = Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models", web_dist_dir=tmp_path / "dist")
    assert PathRedactor.for_settings(settings).redact(text) == expected


# --- T-CORE-01f: log.exception with fake name redacted ---
def test_t_core_01f_log_exception_redacted(clean_logging):
    stream = io.StringIO()
    configure_logging(level="DEBUG", stream=stream)
    log = logging.getLogger("test.exception")

    fake_path = Path(r"C:\Users") / FAKE_NAME / "bad.mp4"
    assert FAKE_NAME in str(fake_path)
    try:
        raise FileNotFoundError(f"cannot open {fake_path}")
    except FileNotFoundError:
        log.exception("failed to process video")

    out = stream.getvalue()
    assert "Traceback (most recent call last)" in out
    assert FAKE_NAME not in out
    assert "FileNotFoundError: cannot open <path>" in out
    # Frames of our own code keep their project-relative location.
    assert f'File "<project>{os.sep}tests{os.sep}unit{os.sep}test_logs.py"' in out
    assert not ABS_PATH_RE.search(out), out


# --- T-CORE-01g: line format: ISO-8601, padded level, logger, [run=-] ---
def test_t_core_01g_line_format(clean_logging):
    stream = io.StringIO()
    configure_logging(level="INFO", stream=stream)
    logging.getLogger("test.format").info("hello world")

    line = stream.getvalue().strip()
    pattern = (
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}\s+INFO\s+test\.format\s+\[run=-\]\s+hello world$"
    )
    assert re.match(pattern, line), f"Line did not match expected format: {line}"


# --- T-CORE-01h: inside run_log: run_id captured, thread context handling ---
def test_t_core_01h_run_log_and_threads(clean_logging, tmp_path: Path):
    stream = io.StringIO()
    configure_logging(level="INFO", stream=stream)
    run_id = "test_run_1234567890_abcdef"

    run_dir = tmp_path / "runs" / run_id
    log = logging.getLogger("taiji_ai.worker")
    with run_log(run_dir, run_id):
        log.info("step 1 running")
        logging.getLogger("external.library").info("external log line")  # third-party style logger

        t1 = threading.Thread(target=lambda: log.info("line from thread without context"))
        t1.start()
        t1.join()

        ctx = contextvars.copy_context()
        t2 = threading.Thread(target=ctx.run, args=(lambda: log.info("line from thread with context"),))
        t2.start()
        t2.join()

    log.info("after run complete")

    content = (run_dir / RUN_LOG_NAME).read_text(encoding="utf-8")
    assert f"run log start: run_id={run_id}" in content
    short_run_id = run_id[:12]
    assert f"[run={short_run_id}] step 1 running" in content
    assert f"[run={short_run_id}] external log line" in content
    assert f"[run={short_run_id}] line from thread with context" in content
    assert "line from thread without context" not in content
    assert "after run complete" not in content

    console_out = stream.getvalue()
    assert "[run=-]" in console_out
    assert "line from thread without context" in console_out
    assert "after run complete" in console_out


def test_t_core_01h_reconfigure_inside_run_still_logs_to_file(clean_logging, tmp_path: Path):
    """F-2: re-configuring puts the file handler first, so it must set run_id itself (its own RunContextFilter)."""
    configure_logging(level="INFO", stream=io.StringIO())
    with run_log(tmp_path / "r", "run_reconf"):
        configure_logging(level="INFO", stream=io.StringIO())
        logging.getLogger("taiji_ai.worker").info("line after reconfigure")

    content = (tmp_path / "r" / RUN_LOG_NAME).read_text(encoding="utf-8")
    assert "[run=run_reconf] line after reconfigure" in content


# --- T-CORE-01i: an exception in run_log propagates and the handler is closed and removed ---
@pytest.mark.parametrize("exc", [RuntimeError("something went wrong"), KeyboardInterrupt(), SystemExit(3)])
def test_t_core_01i_run_log_exception_closes_handler(clean_logging, tmp_path: Path, exc: BaseException):
    configure_logging(level="INFO", stream=io.StringIO())
    run_dir = tmp_path / "run_exc"

    with pytest.raises(type(exc)):
        with run_log(run_dir, "run_boom"):
            raise exc

    log_file = run_dir / RUN_LOG_NAME
    content = log_file.read_text(encoding="utf-8")
    assert content.rstrip().endswith(f"run log end: {type(exc).__name__}")  # BUG-0017: also for cancellation
    assert current_run_id() is None
    root = logging.getLogger()
    assert not any(getattr(h, "baseFilename", None) == str(log_file) for h in root.handlers)
    log_file.unlink()  # on Windows this fails if the handle is still open
    assert not log_file.exists()


# --- T-CORE-01j: input errors & second run appends ---
def test_t_core_01j_input_errors_and_append(clean_logging, tmp_path: Path):
    with pytest.raises(RuntimeError, match="call taiji_ai.logs.configure_logging.*first"):
        with run_log(tmp_path / "r1", "valid_run_id"):
            pass

    configure_logging(level="INFO", stream=io.StringIO())

    for bad_id in ["../traversal", "", "has space", "a" * 65]:
        with pytest.raises(ValueError, match="Invalid run_id"):
            with run_log(tmp_path / "r_bad", bad_id):
                pass

    with run_log(tmp_path / "r_nested", "run1"):
        with pytest.raises(RuntimeError, match="already active"):
            with run_log(tmp_path / "r_nested", "run2"):
                pass

    r_dir = tmp_path / "r_append"
    with run_log(r_dir, "run_app"):
        logging.getLogger("test").info("first attempt")
    with run_log(r_dir, "run_app"):
        logging.getLogger("test").info("second attempt")

    text = (r_dir / RUN_LOG_NAME).read_text(encoding="utf-8")
    assert text.count("run log start: run_id=run_app") == 2
    assert text.index("first attempt") < text.index("second attempt")


# --- T-CORE-01k: configure_logging idempotence & foreign handlers kept ---
def test_t_core_01k_idempotent_and_foreign_handlers(clean_logging):
    root = logging.getLogger()
    foreign_handler = logging.StreamHandler(io.StringIO())
    root.addHandler(foreign_handler)

    h1 = configure_logging(level="INFO")
    assert foreign_handler in root.handlers
    assert h1 in root.handlers

    h2 = configure_logging(level="DEBUG")
    assert foreign_handler in root.handlers
    assert h1 not in root.handlers
    assert h2 in root.handlers
    assert root.level == logging.DEBUG


# --- T-CORE-01l: level from Settings or argument; invalid level raises ---
def test_t_core_01l_log_level_validation(clean_logging):
    configure_logging(level="debug")
    assert logging.getLogger().level == logging.DEBUG
    configure_logging(level="WARNING")
    assert logging.getLogger().level == logging.WARNING
    configure_logging(level=logging.ERROR)
    assert logging.getLogger().level == logging.ERROR
    configure_logging(Settings(log_level="CRITICAL"))
    assert logging.getLogger().level == logging.CRITICAL

    # Only the five documented names are accepted (F-6): aliases are refused like any other word.
    for bad in ["INVALID_LEVEL", "WARN", "NOTSET", "FATAL"]:
        with pytest.raises(ValueError, match="TAIJI_LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL"):
            configure_logging(level=bad)


# --- T-CORE-01m: warnings.warn captured, formatted, and redacted ---
def test_t_core_01m_warnings_captured_and_redacted(clean_logging):
    stream = io.StringIO()
    configure_logging(level="WARNING", stream=stream)

    warnings.warn("this is a test deprecation warning", DeprecationWarning, stacklevel=1)

    out = stream.getvalue()
    assert "DeprecationWarning: this is a test deprecation warning" in out
    assert "py.warnings" in out
    assert str(Path(__file__).resolve()) not in out
    assert f"<project>{os.sep}tests{os.sep}unit{os.sep}test_logs.py" in out


# --- T-CORE-01n: non-ASCII text written to run.log as UTF-8 ---
def test_t_core_01n_non_ascii_utf8_in_run_log(clean_logging, tmp_path: Path):
    configure_logging(level="INFO", stream=io.StringIO())
    run_dir = tmp_path / "utf8_run"

    non_ascii_msg = "Thái Cực Quyền 24 thức: Động tác Dã Mã Phân Tông"
    with run_log(run_dir, "run_utf8"):
        logging.getLogger("taiji.eval").info(non_ascii_msg)

    content = (run_dir / RUN_LOG_NAME).read_text(encoding="utf-8")
    assert non_ascii_msg in content
