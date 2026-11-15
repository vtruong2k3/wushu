from __future__ import annotations

import contextvars
import io
import logging
import re
import tempfile
import threading
import warnings
from pathlib import Path

import pytest

from taiji_ai.config import PROJECT_ROOT, Settings
from taiji_ai.logs import (
    _TAIJI_HANDLER_ATTR,
    RUN_LOG_NAME,
    PathRedactor,
    RunContextFilter,
    configure_logging,
    current_run_id,
    run_log,
)

FAKE_NAME = "Người Tập Giả"


@pytest.fixture
def clean_logging():
    root = logging.getLogger()
    old_handlers = list(root.handlers)
    old_level = root.level
    for h in list(root.handlers):
        if getattr(h, _TAIJI_HANDLER_ATTR, False):
            root.removeHandler(h)
            h.close()
    try:
        yield
    finally:
        for h in list(root.handlers):
            if getattr(h, _TAIJI_HANDLER_ATTR, False) or h not in old_handlers:
                root.removeHandler(h)
                h.close()
        root.handlers = [h for h in old_handlers if not getattr(h, _TAIJI_HANDLER_ATTR, False)]
        root.setLevel(old_level)
        logging.captureWarnings(False)


# --- T-CORE-01a: Unknown absolute paths with fake name redacted to <path> ---
@pytest.mark.parametrize(
    "path_template",
    [
        r"C:\Users\{name}\Videos\routine.mp4",
        r"C:/Users/{name}/Videos/routine.mp4",
        r"c:\users\{name}\videos\routine.mp4",
        r"C:\\Users\\{name}\\Videos\\routine.mp4",
        r"\\nas\share\{name}\routine.mp4",
        r"\\?\C:\Users\{name}\Videos\routine.mp4",
        r"/home/{name}/videos/routine.mp4",
        r"/Users/{name}/videos/routine.mp4",
    ],
)
def test_t_core_01a_absolute_paths_redacted_to_path(path_template: str):
    inp = f"error accessing '{path_template.format(name=FAKE_NAME)}'"
    assert FAKE_NAME in inp  # negative control

    redactor = PathRedactor({})
    redacted = redactor.redact(inp)

    assert FAKE_NAME not in redacted
    assert "<path>" in redacted
    assert redacted == "error accessing '<path>'"


# --- T-CORE-01b: Known roots keep the tail ---
def test_t_core_01b_known_roots_keep_tail(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path / "data",
        models_dir=tmp_path / "models",
        web_dist_dir=tmp_path / "web" / "dist",
    )
    redactor = PathRedactor.for_settings(settings)

    # 1. Data dir
    data_file = settings.data_dir / "runs" / "r1" / "pose_raw.npz"
    s1 = f"wrote artifact {data_file}"
    r1 = redactor.redact(s1)
    assert r1 == r"wrote artifact <data>\runs\r1\pose_raw.npz" or r1 == "wrote artifact <data>/runs/r1/pose_raw.npz"

    # 2. Forward-slash spelling
    s2 = f"wrote {settings.data_dir.as_posix()}/runs/r1/pose_raw.npz"
    assert redactor.redact(s2) == "wrote <data>/runs/r1/pose_raw.npz"

    # 3. Project root
    src_file = PROJECT_ROOT / "src" / "taiji_ai" / "logs.py"
    s3 = f"loaded {src_file}"
    r3 = redactor.redact(s3)
    assert "<project>" in r3
    assert str(src_file) not in r3

    # 4. Longest root wins: if data_dir is inside project_root, <data> wins over <project>
    inside_data = PROJECT_ROOT / "data" / "rec" / "pose.npz"
    redactor_proj = PathRedactor({"<project>": PROJECT_ROOT, "<data>": PROJECT_ROOT / "data"})
    assert redactor_proj.redact(str(inside_data)).startswith("<data>")


# --- T-CORE-01c: Boundary check & over-redaction stops at quote / < ---
def test_t_core_01c_boundary_and_over_redaction_stopping(tmp_path: Path):
    redactor = PathRedactor({"<data>": tmp_path / "data"})

    # Boundary: data2 is NOT <data>
    other_folder = tmp_path / "data2" / "test.txt"
    r = redactor.redact(str(other_folder))
    assert "<data>2" not in r
    assert "<path>" in r

    # Over-redaction stops at quote or <
    msg = f"file '{tmp_path / 'other' / 'bad.mp4'}' was not found; <info> next"
    r_msg = redactor.redact(msg)
    assert r_msg == "file '<path>' was not found; <info> next"


# --- T-CORE-01d: Unsafe roots ignored ---
def test_t_core_01d_unsafe_roots_ignored(monkeypatch):
    # Anchor root (e.g. C:\)
    anchor = Path(Path.cwd().anchor)
    # Home folder root
    home = Path.home()
    # Temp folder root
    temp_dir = Path(tempfile.gettempdir())

    redactor = PathRedactor(
        {
            "<root_drive>": anchor,
            "<home_root>": home,
            "<temp_root>": temp_dir,
        }
    )
    # None of these unsafe roots should keep tails
    secret_home = home / FAKE_NAME / "secret.txt"
    out = redactor.redact(str(secret_home))
    assert "<home_root>" not in out
    assert "<path>" in out
    assert FAKE_NAME not in out


# --- T-CORE-01e: Not paths, left unchanged ---
def test_t_core_01e_not_paths_left_unchanged():
    redactor = PathRedactor({})
    unchanged = [
        "http://127.0.0.1:8007/api/health",
        "https://example.com/api/v1/test",
        "/api/runs/abc",
        "10:22:03",
        "aspect ratio 3:2",
    ]
    for text in unchanged:
        assert redactor.redact(text) == text

    # file:// keeps scheme
    file_url = r"file:///C:/Users/test/file.mp4"
    assert redactor.redact(file_url) == "file:///<path>"


# --- T-CORE-01f: log.exception with fake name redacted ---
def test_t_core_01f_log_exception_redacted(clean_logging):
    stream = io.StringIO()
    configure_logging(level="DEBUG", stream=stream)
    log = logging.getLogger("test.exception")

    fake_path = Path(r"C:\Users") / FAKE_NAME / "bad.mp4"
    try:
        raise FileNotFoundError(f"cannot open {fake_path}")
    except FileNotFoundError:
        log.exception("failed to process video")

    out = stream.getvalue()
    assert FAKE_NAME not in out
    assert "<path>" in out
    assert "FileNotFoundError: cannot open <path>" in out


# --- T-CORE-01g: Line format: ISO-8601, padded level, logger, [run=-] ---
def test_t_core_01g_line_format(clean_logging):
    stream = io.StringIO()
    configure_logging(level="INFO", stream=stream)
    log = logging.getLogger("test.format")
    log.info("hello world")

    line = stream.getvalue().strip()
    # Check format: YYYY-MM-DDTHH:MM:SS.mmm+ZZ:ZZ INFO     test.format [run=-] hello world
    pattern = (
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}\s+INFO\s+test\.format\s+\[run=-\]\s+hello world$"
    )
    assert re.match(pattern, line), f"Line did not match expected format: {line}"


# --- T-CORE-01h: Inside run_log: run_id captured, thread context handling ---
def test_t_core_01h_run_log_and_threads(clean_logging, tmp_path: Path):
    stream = io.StringIO()
    configure_logging(level="INFO", stream=stream)
    run_id = "test_run_1234567890_abcdef"

    run_dir = tmp_path / "runs" / run_id
    with run_log(run_dir, run_id):
        # Assert file handler has RunContextFilter
        root = logging.getLogger()
        file_handlers = [
            h
            for h in root.handlers
            if isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "").endswith(RUN_LOG_NAME)
        ]
        assert len(file_handlers) == 1
        assert any(isinstance(f, RunContextFilter) for f in file_handlers[0].filters)

        log = logging.getLogger("taiji_ai.worker")
        log.info("step 1 running")

        # Third-party style logger
        logging.getLogger("external.library").info("external log line")

        # Thread without context
        t_no_ctx_ran = threading.Event()

        def thread_no_ctx():
            log.info("line from thread without context")
            t_no_ctx_ran.set()

        t1 = threading.Thread(target=thread_no_ctx)
        t1.start()
        t1.join()

        # Thread with copied context
        ctx = contextvars.copy_context()
        t_with_ctx_ran = threading.Event()

        def thread_with_ctx():
            log.info("line from thread with context")
            t_with_ctx_ran.set()

        t2 = threading.Thread(target=ctx.run, args=(thread_with_ctx,))
        t2.start()
        t2.join()

    # Log line after run_log
    log.info("after run complete")

    log_file = run_dir / RUN_LOG_NAME
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")

    # Start line contains full run_id
    assert f"run log start: run_id={run_id}" in content
    # Records inside run_log have [run=<first 12 chars>]
    short_run_id = run_id[:12]
    assert f"[run={short_run_id}] step 1 running" in content
    assert f"[run={short_run_id}] external log line" in content
    assert f"[run={short_run_id}] line from thread with context" in content

    # Thread without context and log after run_log are NOT in run.log
    assert "line from thread without context" not in content
    assert "after run complete" not in content

    # But they are on console stream with run=-
    console_out = stream.getvalue()
    assert "[run=-]" in console_out
    assert "line from thread without context" in console_out
    assert "after run complete" in console_out


# --- T-CORE-01i: Exception in run_log propagates and closes handler ---
def test_t_core_01i_run_log_exception_closes_handler(clean_logging, tmp_path: Path):
    stream = io.StringIO()
    configure_logging(level="INFO", stream=stream)
    run_dir = tmp_path / "run_exc"
    run_id = "run_boom"

    with pytest.raises(RuntimeError, match="something went wrong"):
        with run_log(run_dir, run_id):
            raise RuntimeError("something went wrong")

    log_file = run_dir / RUN_LOG_NAME
    content = log_file.read_text(encoding="utf-8")
    assert "run log end: RuntimeError" in content

    assert current_run_id() is None
    # On Windows, we can remove the file if the handle was closed properly
    log_file.unlink()
    assert not log_file.exists()


# --- T-CORE-01j: Input errors & second run appends ---
def test_t_core_01j_input_errors_and_append(clean_logging, tmp_path: Path):
    # 1. Call before configure_logging
    with pytest.raises(RuntimeError, match="call taiji_ai.logs.configure_logging.*first"):
        with run_log(tmp_path / "r1", "valid_run_id"):
            pass

    configure_logging(level="INFO", stream=io.StringIO())

    # 2. Bad run_id
    for bad_id in ["../traversal", "", "has space", "a" * 65]:
        with pytest.raises(ValueError, match="Invalid run_id"):
            with run_log(tmp_path / "r_bad", bad_id):
                pass

    # 3. Nested run_log
    with run_log(tmp_path / "r_nested", "run1"):
        with pytest.raises(RuntimeError, match="already active"):
            with run_log(tmp_path / "r_nested", "run2"):
                pass

    # 4. Second run_log appends
    r_dir = tmp_path / "r_append"
    with run_log(r_dir, "run_app"):
        logging.getLogger("test").info("first attempt")
    with run_log(r_dir, "run_app"):
        logging.getLogger("test").info("second attempt")

    text = (r_dir / RUN_LOG_NAME).read_text(encoding="utf-8")
    assert text.count("run log start: run_id=run_app") == 2
    assert "first attempt" in text
    assert "second attempt" in text


# --- T-CORE-01k: configure_logging idempotence & preserve foreign handlers ---
def test_t_core_01k_idempotent_and_foreign_handlers(clean_logging):
    root = logging.getLogger()
    foreign_stream = io.StringIO()
    foreign_handler = logging.StreamHandler(foreign_stream)
    root.addHandler(foreign_handler)

    h1 = configure_logging(level="INFO")
    assert foreign_handler in root.handlers
    assert h1 in root.handlers

    h2 = configure_logging(level="DEBUG")
    assert foreign_handler in root.handlers
    assert h1 not in root.handlers
    assert h2 in root.handlers
    assert root.level == logging.DEBUG


# --- T-CORE-01l: Level from Settings or argument; invalid level raises ---
def test_t_core_01l_log_level_validation(clean_logging):
    # Valid level strings
    configure_logging(level="debug")
    assert logging.getLogger().level == logging.DEBUG
    configure_logging(level="WARNING")
    assert logging.getLogger().level == logging.WARNING

    # Invalid level string
    with pytest.raises(ValueError, match="TAIJI_LOG_LEVEL must be one of"):
        configure_logging(level="INVALID_LEVEL")


# --- T-CORE-01m: warnings.warn captured, formatted, and redacted ---
def test_t_core_01m_warnings_captured_and_redacted(clean_logging):
    stream = io.StringIO()
    configure_logging(level="WARNING", stream=stream)

    warnings.warn("this is a test deprecation warning", DeprecationWarning, stacklevel=1)

    out = stream.getvalue()
    assert "DeprecationWarning: this is a test deprecation warning" in out
    assert "py.warnings" in out
    # Absolute path of the current test file should be redacted (<project>\... or <path>)
    assert str(Path(__file__).resolve()) not in out


# --- T-CORE-01n: Non-ASCII text written to run.log as UTF-8 ---
def test_t_core_01n_non_ascii_utf8_in_run_log(clean_logging, tmp_path: Path):
    configure_logging(level="INFO", stream=io.StringIO())
    run_dir = tmp_path / "utf8_run"

    non_ascii_msg = "Thái Cực Quyền 24 thức: Động tác Dã Mã Phân Tông"
    with run_log(run_dir, "run_utf8"):
        logging.getLogger("taiji.eval").info(non_ascii_msg)

    content = (run_dir / RUN_LOG_NAME).read_text(encoding="utf-8")
    assert non_ascii_msg in content
