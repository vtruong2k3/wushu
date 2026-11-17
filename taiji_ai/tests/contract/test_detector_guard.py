"""T-DET-07: the licence guard of the detector comparison (P3.09, DEC-0043).

Ultralytics and the YOLO11 weights are AGPL-3.0 and are used offline for one measurement. The repository must not import
Ultralytics anywhere, the product must not import the offline packages (``taiji_ai.bench``, ``taiji_ai.audit``), and the
registry, the project file and the lock file must not know the model. The scanner is itself tested, so that the guard
fails when an import is added.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "taiji_ai"
OFFLINE = {"bench", "audit"}  # tooling packages: they may import each other and the product, never the other way round


def imported_modules(path: Path) -> list[str]:
    """Every module name imported by a Python file (``import a.b``, ``from a import b`` gives ``a`` and ``a.b``)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
            names += [f"{node.module}.{alias.name}" for alias in node.names]
    return names


def scan(folder: Path, prefixes: tuple[str, ...]) -> list[Path]:
    """The Python files under ``folder`` that import a module equal to or under one of the prefixes."""
    return [
        path
        for path in sorted(folder.rglob("*.py"))
        if any(m == p or m.startswith(p + ".") for m in imported_modules(path) for p in prefixes)
    ]


def files_importing(folders: list[Path], forbidden_prefixes: tuple[str, ...]) -> list[str]:
    """The files (paths from the project root) under ``folders`` that import one of the forbidden modules."""
    return [path.relative_to(ROOT).as_posix() for folder in folders for path in scan(folder, forbidden_prefixes)]


def test_t_det_07_the_scanner_finds_an_import_when_there_is_one(tmp_path: Path):
    (tmp_path / "ok.py").write_text("import numpy\nfrom taiji_ai import pose\n", encoding="utf-8")
    (tmp_path / "bad1.py").write_text("import ultralytics\n", encoding="utf-8")
    (tmp_path / "bad2.py").write_text("from ultralytics.models import YOLO\n", encoding="utf-8")
    (tmp_path / "bad3.py").write_text("def f():\n    import ultralytics.utils\n", encoding="utf-8")
    (tmp_path / "bad4.py").write_text("from taiji_ai import bench\n", encoding="utf-8")
    # a local name, not the package
    (tmp_path / "relative.py").write_text("from . import ultralytics_notes\n", encoding="utf-8")

    assert [p.name for p in scan(tmp_path, ("ultralytics",))] == ["bad1.py", "bad2.py", "bad3.py"]
    assert [p.name for p in scan(tmp_path, ("taiji_ai.bench",))] == ["bad4.py"]


def test_t_det_07_nothing_in_the_repository_imports_ultralytics():
    assert files_importing([SRC, ROOT / "tests", ROOT / "tools"], ("ultralytics",)) == []


def test_t_det_07_the_product_does_not_import_the_offline_packages():
    product = [p for p in SRC.iterdir() if p.is_dir() and p.name not in OFFLINE and not p.name.startswith("__")]
    singles = [p for p in SRC.glob("*.py")]
    hits: list[str] = []
    for folder in product:
        hits += files_importing([folder], ("taiji_ai.bench", "taiji_ai.audit"))
    for path in singles:
        if any(m.startswith(("taiji_ai.bench", "taiji_ai.audit")) for m in imported_modules(path)):
            hits.append(path.relative_to(ROOT).as_posix())
    assert hits == []


def test_t_det_07_the_registry_the_project_file_and_the_lock_know_no_yolo11():
    registry = json.loads((ROOT / "models" / "registry.json").read_text(encoding="utf-8"))
    for model in registry["models"]:
        text = json.dumps(model).lower()
        assert "yolo11" not in text and "ultralytics" not in text, model["name"]
    for name in ("pyproject.toml", "uv.lock"):
        assert "ultralytics" not in (ROOT / name).read_text(encoding="utf-8").lower(), name
