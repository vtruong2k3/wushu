"""T-DATA-01l: the coach review sheet is generated from the ontology file and cannot go stale (X.18).

``tools/render_ontology_review.py`` renders ``Docs/discovery/ontology_review_sheet.md`` (Vietnamese) from
``config/ontology_v0.yaml``. The committed sheet must equal what the tool renders now, so a change of the YAML that
is not followed by a regeneration turns the gate red (AGENTS.md section 4.3: a stale document is a bug).
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

from taiji_ai.config import PROJECT_ROOT
from taiji_ai.schemas.ontology import DEFAULT_ONTOLOGY_PATH, load_ontology, parse_ontology

_tool_path = PROJECT_ROOT / "tools" / "render_ontology_review.py"
_spec = importlib.util.spec_from_file_location("render_ontology_review", _tool_path)
assert _spec is not None and _spec.loader is not None
tool = importlib.util.module_from_spec(_spec)
sys.modules["render_ontology_review"] = tool
_spec.loader.exec_module(tool)

REGENERATE = r".venv\Scripts\python.exe tools\render_ontology_review.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


@pytest.fixture(scope="module")
def shipped_sheet() -> str:
    onto = load_ontology(DEFAULT_ONTOLOGY_PATH)
    return tool.render_sheet(onto, tool.yaml_digest(_text(DEFAULT_ONTOLOGY_PATH)))


def _row(sheet: str, action_id: str) -> str:
    rows = [line for line in sheet.splitlines() if line.startswith(f"| {action_id} |")]
    assert len(rows) == 1, f"{action_id}: expected one table row, found {len(rows)}"
    return rows[0]


def test_t_data_01l_the_sheet_has_one_row_per_action(shipped_sheet):
    for i in range(1, 25):
        _row(shipped_sheet, f"A{i:02d}")
    assert len(re.findall(r"^\| A\d\d \|", shipped_sheet, flags=re.M)) == 24


def test_t_data_01l_rows_show_names_repetitions_and_side_order(shipped_sheet):
    a02 = _row(shipped_sheet, "A02")
    assert "左右野马分鬃" in a02 and "Tả hữu dã mã phân tông" in a02
    assert "trái, phải" in a02 and "trái → phải → trái" in a02
    a18 = _row(shipped_sheet, "A18")
    assert "phải → trái" in a18


def test_t_data_01l_an_alternating_action_without_a_sequence_says_it_is_not_determined(shipped_sheet):
    for action_id in ("A06", "A10"):
        assert "chưa xác định" in _row(shipped_sheet, action_id), action_id
    assert "chưa xác định" not in _row(shipped_sheet, "A02")


def test_t_data_01l_a_single_side_action_shows_no_order(shipped_sheet):
    row = _row(shipped_sheet, "A01")
    assert "không phân biệt" in row
    assert "chưa xác định" not in row


def test_t_data_01l_the_questions_list_the_undecided_actions_and_the_shared_techniques(shipped_sheet):
    assert "Cần điền cho các dòng chưa xác định: A06, A10." in shipped_sheet
    assert "(A07/A08, A09/A11, A16/A17)" in shipped_sheet


def test_t_data_01l_question_4_states_the_working_convention_and_asks_the_coach(shipped_sheet):
    """X.20: the convention for the side label is shown to the coach, who may confirm or change it."""
    m = re.search(r"^4\. .*?(?=^5\. )", shipped_sheet, flags=re.M | re.S)
    assert m, "question 4 was not found"
    q4 = m.group(0)
    assert "Quy ước tạm đang dùng" in q4
    assert "chữ trái hoặc phải trong tên chuẩn của thức" in q4
    assert "chân bước ra trước" in q4
    assert "chờ thầy/cô xác nhận" in q4
    assert "hay muốn đổi" in q4


def test_t_data_01l_a_draft_is_labelled_unconfirmed(shipped_sheet):
    assert "chưa xác nhận" in shipped_sheet


def _confirmed_doc() -> dict:
    return {
        "schema_version": "ontology/1",
        "ontology_version": "v0",
        "form": {
            "id": "demo",
            "name_en": "Demo",
            "expected_actions": 1,
            "status": "confirmed",
            "confirmed_by": "H1",
            "confirmed_at": "2026-12-01",
        },
        "sides": ["left", "right", "none"],
        "view_categories": ["front", "side", "oblique", "back", "unknown"],
        "flags": ["orientation_change", "occlusion", "perspective_shift"],
        "actions": [
            {
                "id": "A01",
                "slug": "opening",
                "technique": "opening",
                "name_en": "Opening",
                "name_zh": "zh",
                "name_vi": "vi",
                "sides": ["none"],
                "repetitions": 1,
            }
        ],
    }


def test_t_data_01l_a_confirmed_form_shows_role_and_date_not_the_draft_label():
    sheet = tool.render_sheet(parse_ontology(_confirmed_doc()), "0" * 12)
    assert "H1" in sheet and "2026-12-01" in sheet
    assert "chưa xác nhận" not in sheet


def test_t_data_01l_the_digest_ignores_line_ends_and_follows_the_text():
    assert tool.yaml_digest("a\r\nb\r\n") == tool.yaml_digest("a\nb\n")
    assert tool.yaml_digest("a\nb\n") != tool.yaml_digest("a\nc\n")
    assert re.fullmatch(r"[0-9a-f]{12}", tool.yaml_digest("x"))


def test_t_data_01l_the_sheet_embeds_the_digest_it_was_given(shipped_sheet):
    digest = tool.yaml_digest(_text(DEFAULT_ONTOLOGY_PATH))
    assert tool.read_sheet_digest(shipped_sheet) == digest
    assert tool.read_sheet_digest("no digest here") is None


def test_t_data_01l_the_committed_sheet_equals_what_the_tool_renders_now(shipped_sheet):
    """Stale guard: edit the YAML, then regenerate the sheet."""
    assert tool.SHEET_PATH.exists(), f"the sheet is missing; generate it with: {REGENERATE}"
    committed = _text(tool.SHEET_PATH)
    assert tool.read_sheet_digest(committed) == tool.yaml_digest(_text(DEFAULT_ONTOLOGY_PATH)), (
        f"the sheet was made from another version of the YAML; regenerate it with: {REGENERATE}"
    )
    assert committed == shipped_sheet, f"the sheet differs from the tool output; regenerate it with: {REGENERATE}"


def test_t_data_01l_main_writes_the_sheet_and_check_reports_stale_and_missing(tmp_path, capsys, shipped_sheet):
    out = tmp_path / "sheet.md"
    assert tool.main(["--check", "--out", str(out)]) == 1  # missing
    assert tool.main(["--out", str(out)]) == 0
    assert _text(out) == shipped_sheet
    assert tool.main(["--check", "--out", str(out)]) == 0  # fresh
    out.write_text(_text(out).replace(tool.yaml_digest(_text(DEFAULT_ONTOLOGY_PATH)), "0" * 12), encoding="utf-8")
    assert tool.main(["--check", "--out", str(out)]) == 1  # stale
    capsys.readouterr()


def test_t_data_01l_main_rejects_an_invalid_ontology_file(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("just a string\n", encoding="utf-8")
    assert tool.main(["--ontology", str(bad), "--out", str(tmp_path / "sheet.md")]) == 2
    assert not (tmp_path / "sheet.md").exists()
    assert "mapping" in capsys.readouterr().err
