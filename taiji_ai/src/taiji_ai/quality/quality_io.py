"""Save and load ``quality.json``, the report of the quality layer (schema ``quality/1``, P4.07).

The file is the JSON of ``taiji_ai.schemas.quality.QualityReport``: counts with their denominators (by interval, by
joint, by reason, by gap outcome), the clock of the run, the parameters of the stages as used and the warnings.
It has no keypoint value, no name and no path. The two layers of the quality stage that are arrays
(``pose_masked.npz``, ``pose_filtered.npz``) are written by ``quality/layers_io.py`` (X.29).

Writing is atomic (a temporary file, ``fsync``, ``os.replace``: a failed write leaves the old file and no temporary one)
and deterministic (the same report gives the same bytes); the caller chooses the path (P7: ``runs/<run_id>/``) and the
folder is created. ``save_quality`` returns the SHA-256 of the file for the run manifest. Loading is strict: another
version, a missing or unknown field, a wrong type, a NaN, a count that disagrees with the others or a file that is not
UTF-8 JSON is a ``ManifestError`` that names the field; an old file is never upgraded silently.
"""

from __future__ import annotations

import logging
from pathlib import Path

from taiji_ai.schemas._base import read_manifest, write_manifest
from taiji_ai.schemas.quality import QualityReport
from taiji_ai.store.artifacts import sha256_file

log = logging.getLogger(__name__)


def save_quality(path: str | Path, report: QualityReport) -> str:
    """Write ``report`` as ``quality.json`` at ``path`` atomically; return the SHA-256 (hex) of the file.

    Raises ``TypeError`` for anything that is not a ``QualityReport`` and ``OSError`` if the file cannot be written
    (the old file, if any, is left as it was).
    """
    if not isinstance(report, QualityReport):
        raise TypeError(f"report must be a QualityReport, got {type(report).__name__}")
    written = write_manifest(path, report)
    digest = sha256_file(written)
    log.info("quality report written (%d intervals, %d warnings)", len(report.intervals), len(report.warnings))
    return digest


def load_quality(path: str | Path) -> QualityReport:
    """Read and validate ``quality.json``.

    Raises ``FileNotFoundError`` if the file does not exist and ``ManifestError`` if it is not a valid report of
    schema ``quality/1``.
    """
    return read_manifest(path, QualityReport)
