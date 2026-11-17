"""Headers of ``pose_masked.npz`` and ``pose_filtered.npz`` (schemas ``pose_masked/1`` and ``pose_filtered/1``, X.29).

Each archive holds data arrays (documented in ``taiji_ai.quality.layers_io``), a 0-d text array ``schema_version`` and
a 0-d text array ``meta_json``: one of the models below as JSON. Units and coordinates: positions are pixels of the
upright image (x right, y down), times seconds from the stream start. Floats are never NaN or infinite (AGENTS.md
section 6). The headers hold no path, no file name and no person's name: the only identifier is the ``recording_id``,
as in ``pose_raw/1``. The wall clock of a run is not here: it belongs to the run manifest (P7).

``data_sources`` is the provenance that AGENTS.md section 9.4.6 asks of a derived artifact: the dataset ids of the
registry with their licence text. An **empty list** says that the recording is one of ours and that its restrictions
are those of ``recording_id`` in the store (consent scope, section 9.5); a recording that comes from a dataset names
it, and a source with a non-commercial licence makes the artifact non-commercial. The caller (P7) fills it:
``pose_raw/1`` has no such field.
"""

from __future__ import annotations

import math
from typing import Literal, Self

from pydantic import Field, model_validator

from taiji_ai.schemas._base import UUID4_RE, FrozenModel, Manifest, NonNeg, NonNegInt, PosInt, Positive
from taiji_ai.schemas.quality import MaskParamsRecord, QualityParamsRecord, StrictBool, SwapParamsRecord

DATASET_ID_RE = r"^D\d{2,}$"  # the ids of ``Docs/DATASET_REGISTRY_TAIJI.md``
LICENSE_RE = r"^[^\x00-\x1f\x7f]{1,80}$"  # one line of text, 80 characters at most
N_JOINTS = 26
_RATE_TOL = 1e-6  # sampling_hz * step_s is 1 up to this


class DataSource(FrozenModel):
    """A dataset that the recording belongs to: its id in the registry and the licence that governs it."""

    dataset_id: str = Field(pattern=DATASET_ID_RE)
    license: str = Field(pattern=LICENSE_RE)


def _distinct(sources: tuple[DataSource, ...]) -> None:
    ids = [s.dataset_id for s in sources]
    if len(set(ids)) != len(ids):
        raise ValueError("data_sources must name each dataset once")


class MaskedCounts(FrozenModel):
    """Counts of ``pose_masked.npz``; they must agree with the arrays."""

    n_rows: PosInt  # rows of the target track (the margins of the segment included)


class PoseMaskedMeta(Manifest):
    """``meta_json`` of ``pose_masked.npz``: the mask layer and the swap flags that were read from it."""

    schema_version: Literal["pose_masked/1"]
    skeleton: Literal["halpe26/1"]  # the reader compares it with ``taiji_ai.pose.skeleton.SKELETON_ID``
    recording_id: str = Field(pattern=UUID4_RE)
    mask: MaskParamsRecord  # the parameters of the mask as used
    swap: SwapParamsRecord  # the parameters of the swap flag as used (its pairs say where a flag may be)
    counts: MaskedCounts
    data_sources: tuple[DataSource, ...]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        _distinct(self.data_sources)
        return self


class FilteredTimeline(FrozenModel):
    """The two clocks of ``pose_filtered.npz``: the rows of the video and the grid the layer lives on."""

    n_rows: PosInt  # rows of the video (the target track)
    n_grid_rows: PosInt  # rows of the layer
    resampled: StrictBool  # the timeline was not uniform: the grid is not the rows
    step_s: Positive | None  # [s] the interval of the grid; null for one row
    sampling_hz: Positive | None  # [Hz] 1 / step_s
    snap_s: NonNeg  # [s] a grid time within this of a row is that row; 0 when the grid is the rows

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if not self.resampled and self.n_grid_rows != self.n_rows:
            raise ValueError("n_grid_rows must equal n_rows when the timeline was not resampled")
        if (self.step_s is None) != (self.sampling_hz is None):
            raise ValueError("step_s and sampling_hz must both be given or both be null")
        if self.step_s is not None and self.sampling_hz is not None:
            if not math.isclose(self.sampling_hz * self.step_s, 1.0, rel_tol=_RATE_TOL):
                raise ValueError("sampling_hz must be 1 / step_s")
        return self


class FilteredCounts(FrozenModel):
    """Counts of ``pose_filtered.npz``; they must agree with the arrays."""

    n_mixed_rows: NonNegInt  # grid rows that are linear mixes of two rows of the video
    n_filtered_cells: NonNegInt  # cells whose value comes from the low-pass filter


class PoseFilteredMeta(Manifest):
    """``meta_json`` of ``pose_filtered.npz``: the final layer on the grid and the map back to the rows."""

    schema_version: Literal["pose_filtered/1"]
    skeleton: Literal["halpe26/1"]
    recording_id: str = Field(pattern=UUID4_RE)
    params: QualityParamsRecord  # the parameters of every stage as used (the Hampel floor in pixels)
    timeline: FilteredTimeline
    counts: FilteredCounts
    data_sources: tuple[DataSource, ...]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        _distinct(self.data_sources)
        if self.counts.n_mixed_rows > self.timeline.n_grid_rows:
            raise ValueError("n_mixed_rows must not exceed n_grid_rows")
        if self.counts.n_filtered_cells > N_JOINTS * self.timeline.n_grid_rows:
            raise ValueError("n_filtered_cells must not exceed the cells of the layer (n_grid_rows x 26)")
        return self
