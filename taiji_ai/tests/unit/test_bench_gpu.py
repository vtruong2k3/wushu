"""T-BENCH-04: the VRAM sampler with a fake NVML, and the real NVML when there is a GPU (P3.07)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from taiji_ai.bench import BenchError
from taiji_ai.bench.gpu import VramSampler, try_open_nvml, vram_unavailable


class FakeNvml:
    """Answers with scripted values of the device memory used [MiB]."""

    def __init__(self, used: list[float], total: float = 12288.0, fail_after: int | None = None):
        self.used, self.total, self.fail_after = list(used), total, fail_after
        self.calls = 0
        self.closed = False

    def used_mib(self) -> float:
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise RuntimeError("NVML went away")
        return self.used.pop(0) if len(self.used) > 1 else self.used[0]

    def total_mib(self) -> float:
        return self.total

    def utilisation_pct(self) -> float:
        return 15.0

    def device_name(self) -> str:
        return "Fake GPU"

    def driver_version(self) -> str:
        return "1.0"

    def close(self) -> None:
        self.closed = True


# --- T-BENCH-04a: baseline, peaks, drift ----------------------------------------------------------------------------
def test_t_bench_04a_baseline_peaks_and_drift_from_the_samples_of_each_phase():
    sampler = VramSampler(FakeNvml([1000, 1010, 1005, 1100, 1500, 1600, 3000, 4200, 4100, 4000, 4300]))
    sampler.phase("baseline")
    for _ in range(4):
        sampler.sample_once()
    sampler.phase("load")
    for _ in range(2):
        sampler.sample_once()
    sampler.phase("warmup")
    for _ in range(3):
        sampler.sample_once()
    sampler.phase("measured")
    for _ in range(2):
        sampler.sample_once()

    s = sampler.summary()

    assert s["measured"] is True
    assert s["baseline_mib"] == 1007.5 and s["drift_mib"] == 100.0  # median and max - min of the baseline phase
    assert s["peaks_mib"] == {"load": 1600.0, "warmup": 4200.0, "measured": 4300.0}
    assert s["peak_total_mib"] == 4300.0 and s["peak_delta_mib"] == pytest.approx(4300.0 - 1007.5)
    assert s["total_mib"] == 12288.0 and s["n_samples"] == 11
    assert s["device"] == "Fake GPU" and s["driver"] == "1.0"


def test_t_bench_04a_the_peak_is_not_taken_from_the_baseline_phase():
    sampler = VramSampler(FakeNvml([5000, 5000, 1000, 1000]))
    sampler.phase("baseline")
    sampler.sample_once()
    sampler.sample_once()
    sampler.phase("measured")
    sampler.sample_once()
    sampler.sample_once()
    s = sampler.summary()
    assert s["baseline_mib"] == 5000.0 and s["peak_total_mib"] == 1000.0 and s["peak_delta_mib"] == -4000.0


def test_t_bench_04a_a_sample_before_any_phase_or_a_summary_without_a_baseline_is_refused():
    sampler = VramSampler(FakeNvml([1000]))
    with pytest.raises(BenchError, match="phase"):
        sampler.sample_once()
    sampler.phase("measured")
    sampler.sample_once()
    with pytest.raises(BenchError, match="baseline"):
        sampler.summary()


def test_t_bench_04a_the_thread_samples_and_stops_and_can_run_again():
    sampler = VramSampler(FakeNvml([1000.0]), interval_s=0.001)
    sampler.phase("baseline")
    sampler.start()
    deadline = time.monotonic() + 3.0
    while sampler.n_samples < 5 and time.monotonic() < deadline:
        time.sleep(0.002)
    sampler.stop()
    first = sampler.n_samples
    assert first >= 5 and not sampler.running
    time.sleep(0.02)
    assert sampler.n_samples == first  # stopped: nothing more arrives
    sampler.stop()  # a second stop is harmless
    sampler.start()
    deadline = time.monotonic() + 3.0
    while sampler.n_samples < first + 3 and time.monotonic() < deadline:
        time.sleep(0.002)
    sampler.stop()
    assert sampler.n_samples >= first + 3


def test_t_bench_04a_a_failing_call_in_the_thread_is_raised_at_stop_not_lost():
    sampler = VramSampler(FakeNvml([1000.0], fail_after=3), interval_s=0.001)
    sampler.phase("baseline")
    sampler.start()
    deadline = time.monotonic() + 3.0
    while sampler.running and time.monotonic() < deadline:
        time.sleep(0.002)
    with pytest.raises(BenchError, match="NVML went away"):
        sampler.stop()
    assert sampler.n_samples == 3


def test_t_bench_04a_the_sampler_as_a_context_manager_stops_the_thread():
    with VramSampler(FakeNvml([1000.0]), interval_s=0.001) as sampler:
        sampler.phase("baseline")
        assert sampler.running
    assert not sampler.running


def test_t_bench_04a_bad_interval_is_refused():
    for bad in (0.0, -0.01, float("nan")):
        with pytest.raises(ValueError):
            VramSampler(FakeNvml([1.0]), interval_s=bad)


# --- T-BENCH-04b: no NVML, no number --------------------------------------------------------------------------------
def test_t_bench_04b_without_nvml_the_result_says_not_measured_and_why(tmp_path: Path):
    backend, reason = try_open_nvml(dll_path=tmp_path / "no_such_nvml.dll")
    assert backend is None and reason and "nvml" in reason.lower()
    assert vram_unavailable(reason) == {"measured": False, "reason": reason}


def test_t_bench_04b_a_library_that_is_not_nvml_is_refused(tmp_path: Path):
    fake = tmp_path / "not_nvml.dll"
    fake.write_bytes(b"this is not a library")
    backend, reason = try_open_nvml(dll_path=fake)
    assert backend is None and reason


# --- T-BENCH-04c: the real NVML -------------------------------------------------------------------------------------
@pytest.mark.gpu
def test_t_bench_04c_the_real_nvml_gives_a_plausible_used_memory():
    backend, reason = try_open_nvml()
    if backend is None:
        pytest.skip(f"NVML not available: {reason}")
    try:
        total = backend.total_mib()
        assert backend.device_name() and backend.driver_version()
        assert 1024.0 <= total <= 262144.0
        assert 0.0 <= backend.utilisation_pct() <= 100.0
        with VramSampler(backend, interval_s=0.02) as sampler:
            sampler.phase("baseline")
            time.sleep(0.3)
        s = sampler.summary()
        assert s["measured"] is True and s["n_samples"] >= 5
        assert 0.0 < s["baseline_mib"] < total and s["total_mib"] == total
    finally:
        backend.close()
