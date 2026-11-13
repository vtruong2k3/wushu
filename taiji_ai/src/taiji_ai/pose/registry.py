"""Model registry: the only way the pipeline locates model files.

Models are fetched once with ``tools/fetch_models.py``. At load time every file's SHA-256 is
checked against ``models/registry.json``; a mismatch or missing file raises
:class:`ModelIntegrityError`. Nothing here downloads anything.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from taiji_ai.store.artifacts import sha256_file


class ModelIntegrityError(RuntimeError):
    """Model file missing or its hash does not match the registry."""


@dataclass(frozen=True)
class ModelEntry:
    name: str
    role: str
    file: str
    sha256: str
    input_size: tuple[int, int]
    path: Path
    skeleton: str | None = None


class ModelRegistry:
    def __init__(self, registry_path: str | Path, verify: bool = True):
        self.path = Path(registry_path)
        if not self.path.exists():
            raise ModelIntegrityError(f"registry not found: {self.path} (run tools/fetch_models.py once)")
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if raw.get("schema_version") != "model-registry/1":
            raise ModelIntegrityError(f"unsupported registry schema: {raw.get('schema_version')}")
        base = self.path.parent
        self.entries: dict[str, ModelEntry] = {}
        for e in raw["models"]:
            entry = ModelEntry(
                name=e["name"],
                role=e["role"],
                file=e["file"],
                sha256=e["sha256"],
                input_size=tuple(e["input_size"]),  # type: ignore[arg-type]
                path=base / e["file"],
                skeleton=e.get("skeleton"),
            )
            if verify:
                self._verify(entry)
            self.entries[entry.name] = entry

    @staticmethod
    def _verify(entry: ModelEntry) -> None:
        if not entry.path.exists():
            raise ModelIntegrityError(f"model file missing: {entry.path}")
        actual = sha256_file(entry.path)
        if actual != entry.sha256:
            raise ModelIntegrityError(
                f"sha256 mismatch for {entry.name}: expected {entry.sha256[:12]}…, got {actual[:12]}…"
            )

    def by_role(self, role: str) -> ModelEntry:
        matches = [e for e in self.entries.values() if e.role == role]
        if len(matches) != 1:
            raise ModelIntegrityError(f"expected exactly one model with role={role!r}, found {len(matches)}")
        return matches[0]

    def fingerprint(self) -> dict[str, str]:
        """name -> sha256, for run manifests and cache keys."""
        return {e.name: e.sha256 for e in self.entries.values()}
