"""GPU memory for the benchmark (P3.07): NVML through ``ctypes`` and a sampler of the device memory used.

On this machine (Windows, WDDM) ``nvidia-smi`` cannot tell the memory of one process (``[N/A]``); the **device total**
can be read. The sampler reads it every few milliseconds while the models run, in labelled phases. The memory of the
process is then ``peak total - baseline``, where the baseline is the median of the samples taken before the models were
loaded: it includes what the desktop and other programs hold, so the baseline drift (max - min of the baseline samples)
is reported as the uncertainty. ONNX Runtime keeps its memory arena, so a peak is the memory the process **holds**,
not the minimum it would need.

NVML is the driver's own library (``nvml.dll`` installed with the driver, proprietary, not bundled here), called
through ``ctypes``: no new dependency. When it cannot be loaded the result says ``measured: false`` with the reason; a
number is never invented.
"""

from __future__ import annotations

import ctypes
import logging
import math
import os
import statistics
import sys
import threading
from pathlib import Path
from typing import Any, Protocol

from taiji_ai.bench import BenchError

log = logging.getLogger(__name__)

_MIB = float(2**20)


class NvmlBackend(Protocol):
    """What the sampler needs: the real ``CtypesNvml`` or a fake in tests."""

    def used_mib(self) -> float: ...
    def total_mib(self) -> float: ...
    def utilisation_pct(self) -> float: ...
    def device_name(self) -> str: ...
    def driver_version(self) -> str: ...
    def close(self) -> None: ...


class _Memory(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]


class _Utilisation(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


def _default_library() -> str:
    if sys.platform == "win32":
        return str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvml.dll")
    return "libnvidia-ml.so.1"


class CtypesNvml:
    """NVML device 0 through ``ctypes``. Raises ``BenchError`` when the library or a call is not there."""

    def __init__(self, dll_path: Path | str | None = None, index: int = 0):
        path = str(dll_path) if dll_path is not None else _default_library()
        try:
            self._dll: Any = ctypes.CDLL(path)
        except OSError as exc:
            raise BenchError(f"the NVML library could not be loaded ({type(exc).__name__}: {exc})") from exc
        try:
            self._init = self._dll.nvmlInit_v2
            self._shutdown = self._dll.nvmlShutdown
            self._handle_of = self._dll.nvmlDeviceGetHandleByIndex_v2
            self._memory = self._dll.nvmlDeviceGetMemoryInfo
            self._name = self._dll.nvmlDeviceGetName
            self._driver = self._dll.nvmlSystemGetDriverVersion
            self._util = self._dll.nvmlDeviceGetUtilizationRates
        except AttributeError as exc:
            raise BenchError(f"the library is not NVML: {exc}") from exc
        self._check(self._init(), "nvmlInit_v2")
        self._open = True
        self._handle = ctypes.c_void_p()
        try:
            self._check(
                self._handle_of(ctypes.c_uint(index), ctypes.byref(self._handle)), "nvmlDeviceGetHandleByIndex_v2"
            )
        except BenchError:
            self.close()
            raise

    @staticmethod
    def _check(code: int, name: str) -> None:
        if code != 0:
            raise BenchError(f"NVML {name} failed with code {code}")

    def used_mib(self) -> float:
        info = _Memory()
        self._check(self._memory(self._handle, ctypes.byref(info)), "nvmlDeviceGetMemoryInfo")
        return info.used / _MIB

    def total_mib(self) -> float:
        info = _Memory()
        self._check(self._memory(self._handle, ctypes.byref(info)), "nvmlDeviceGetMemoryInfo")
        return info.total / _MIB

    def utilisation_pct(self) -> float:
        info = _Utilisation()
        self._check(self._util(self._handle, ctypes.byref(info)), "nvmlDeviceGetUtilizationRates")
        return float(info.gpu)

    def device_name(self) -> str:
        buffer = ctypes.create_string_buffer(96)
        self._check(self._name(self._handle, buffer, ctypes.c_uint(96)), "nvmlDeviceGetName")
        return buffer.value.decode("utf-8", errors="replace")

    def driver_version(self) -> str:
        buffer = ctypes.create_string_buffer(80)
        self._check(self._driver(buffer, ctypes.c_uint(80)), "nvmlSystemGetDriverVersion")
        return buffer.value.decode("utf-8", errors="replace")

    def close(self) -> None:
        if self._open:
            self._open = False
            self._shutdown()


def try_open_nvml(dll_path: Path | str | None = None) -> tuple[NvmlBackend | None, str | None]:
    """``(backend, None)``, or ``(None, reason)`` when NVML is not available."""
    try:
        return CtypesNvml(dll_path), None
    except BenchError as exc:
        return None, str(exc)


def vram_unavailable(reason: str | None) -> dict[str, Any]:
    """The VRAM entry of a report when nothing could be measured."""
    return {"measured": False, "reason": reason}


class VramSampler:
    """Samples ``backend.used_mib()`` into labelled phases, by hand (``sample_once``) or from a thread (``start``).

    Call ``phase(label)`` first; ``baseline`` is the phase whose median and spread give the baseline. A failure in the
    thread stops it and is raised by ``stop()`` (never lost).
    """

    def __init__(self, backend: NvmlBackend, interval_s: float = 0.02):
        if not (math.isfinite(interval_s) and interval_s > 0.0):
            raise ValueError(f"interval_s must be a finite number > 0, got {interval_s!r}")
        self._backend = backend
        self._interval = interval_s
        self._lock = threading.Lock()
        self._phase: str | None = None
        self._samples: list[tuple[str, float]] = []
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._error: BaseException | None = None

    @property
    def n_samples(self) -> int:
        with self._lock:
            return len(self._samples)

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def phase(self, label: str) -> None:
        with self._lock:
            self._phase = label

    def _take(self, label: str) -> None:
        used = self._backend.used_mib()
        with self._lock:
            self._samples.append((label, used))

    def sample_once(self) -> None:
        with self._lock:
            label = self._phase
        if label is None:
            raise BenchError("call phase() before sampling")
        self._take(label)

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                label = self._phase
            if label is not None:
                try:
                    self._take(label)
                except BaseException as exc:  # noqa: BLE001 - kept and re-raised by stop(); a thread must not die silently
                    self._error = exc
                    return
            self._stop.wait(self._interval)

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._error = None
        self._thread = threading.Thread(target=self._run, name="vram-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=5.0)
        error, self._error = self._error, None
        if error is not None:
            raise BenchError(f"the VRAM sampler failed: {error}") from error

    def __enter__(self) -> VramSampler:
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()

    def summary(self) -> dict[str, Any]:
        """Baseline, drift, the peak of each later phase and the overall peak (all MiB of the device total)."""
        with self._lock:
            samples = list(self._samples)
        base = [v for label, v in samples if label == "baseline"]
        if not base:
            raise BenchError("no baseline samples: sample the 'baseline' phase before the models are loaded")
        peaks: dict[str, float] = {}
        for label, value in samples:
            if label != "baseline":
                peaks[label] = max(peaks.get(label, value), value)
        baseline = float(statistics.median(base))
        peak_total = max(peaks.values()) if peaks else None
        return {
            "measured": True,
            "device": self._backend.device_name(),
            "driver": self._backend.driver_version(),
            "total_mib": self._backend.total_mib(),
            "baseline_mib": baseline,
            "drift_mib": float(max(base) - min(base)),
            "peaks_mib": peaks,
            "peak_total_mib": peak_total,
            "peak_delta_mib": None if peak_total is None else peak_total - baseline,
            "n_samples": len(samples),
        }
