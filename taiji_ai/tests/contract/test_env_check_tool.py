"""BUG-0076: ``tools/env_check.py`` writes only Markdown on stdout.

The documented use is ``env_check.py > hardware_inventory.md``. rtmlib prints
``load <model path> with <backend> backend`` on stdout when it loads a model, and those lines landed above the heading
of the tracked inventory file. The tool must keep every line of third-party stdout out of the Markdown (it goes to
stderr) and must still run the GPU smoke test.

The tests run the real ``__main__`` block of the script in this process, with the registry and the pose estimator
replaced by stubs: the estimator prints a library-like line at construction and at every call, and counts its prints,
so no model, no GPU and no file of the project is needed.
"""

from __future__ import annotations

import io
import runpy
import sys
from pathlib import Path

import numpy as np
import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "env_check.py"
LIBRARY_LINE = "LIBRARY-NOISE load <model path> with onnxruntime backend"
HEADING = "# Environment inventory"


class _Registry:
    """Stands in for ``ModelRegistry``: no models listed, so the Models section is empty."""

    entries: dict = {}  # noqa: RUF012 - a read-only stub

    def __init__(self, path: object) -> None:
        pass


class _Estimator:
    """Stands in for ``PoseEstimator``: prints like rtmlib does and counts the lines it printed."""

    printed = 0
    line = LIBRARY_LINE

    def __init__(self, registry: object, device: str = "cuda", require_gpu: bool = True) -> None:
        self._say()
        self.providers = {"det": "StubProvider", "pose": "StubProvider"}

    @classmethod
    def _say(cls) -> None:
        cls.printed += 1
        print(cls.line)

    def detect(self, frame_bgr: np.ndarray) -> np.ndarray:
        self._say()
        return np.zeros((0, 4), np.float32)

    def estimate(self, frame_bgr: np.ndarray, bboxes: np.ndarray) -> None:
        self._say()


def run_tool(monkeypatch: pytest.MonkeyPatch, *argv: str, line: str = LIBRARY_LINE) -> None:
    """Run the ``__main__`` block of the script with the stubs in place of the two classes it imports at call time."""
    _Estimator.printed = 0
    _Estimator.line = line
    monkeypatch.setattr("taiji_ai.pose.registry.ModelRegistry", _Registry)
    monkeypatch.setattr("taiji_ai.pose.rtm.PoseEstimator", _Estimator)
    monkeypatch.setattr(sys, "argv", [str(TOOL), *argv])
    try:
        runpy.run_path(str(TOOL), run_name="__main__")
    except SystemExit as stop:
        assert stop.code in (None, 0)


def test_bug_0076_library_stdout_stays_out_of_the_inventory_markdown(monkeypatch, capsys):
    run_tool(monkeypatch, "--gpu-smoke")
    out, err = capsys.readouterr()
    assert _Estimator.printed >= 3  # the stub did print: at construction, in detect and in estimate
    assert out.splitlines()[0] == HEADING
    assert LIBRARY_LINE not in out
    assert err.count(LIBRARY_LINE) == _Estimator.printed  # every line went to stderr, none was lost


def test_bug_0076_the_gpu_smoke_part_still_runs_and_reports(monkeypatch, capsys):
    run_tool(monkeypatch, "--gpu-smoke")
    out, _ = capsys.readouterr()
    assert "## GPU smoke test" in out
    assert "StubProvider" in out
    assert "- detector:" in out and "ms/frame" in out


def test_bug_0076_library_text_that_stderr_cannot_encode_does_not_stop_the_tool(monkeypatch):
    """A Windows console may encode stderr in a legacy code page: a library line with a character outside it (a model
    folder with an accent) must not raise ``UnicodeEncodeError`` in the middle of the inventory."""
    stdout = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
    stderr = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    # an accent (outside ASCII) and a lone surrogate (what a path with undecodable bytes becomes; no encoding holds it)
    run_tool(monkeypatch, "--gpu-smoke", line="LIBRARY-NOISE café \udc80")
    stdout.flush()
    stderr.flush()
    assert stdout.buffer.getvalue().decode("utf-8").splitlines()[0] == HEADING
    assert "LIBRARY-NOISE café ?".encode() in stderr.buffer.getvalue()  # UTF-8, the surrogate replaced, no error


def test_bug_0076_without_the_smoke_test_no_model_is_loaded(monkeypatch, capsys):
    run_tool(monkeypatch)
    out, err = capsys.readouterr()
    assert _Estimator.printed == 0
    assert out.splitlines()[0] == HEADING
    assert "GPU smoke test" not in out
    assert LIBRARY_LINE not in err
