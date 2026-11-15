"""Render the coach review sheet of the ontology (X.18).

Reads ``config/ontology_v0.yaml`` and writes ``Docs/discovery/ontology_review_sheet.md`` (Vietnamese, like the other
coach-facing files): a 24-row table the coach ticks or corrects, the open questions in plain words and a sign-off block.
The sheet embeds the first 12 hex characters of the SHA-256 of the YAML (line ends normalised to LF); a unit test
compares the committed sheet with the tool output, so a change of the YAML without a regeneration fails the gate.

Usage (from ``taiji_ai/``)::

    .venv\\Scripts\\python.exe tools\\render_ontology_review.py            # write the sheet
    .venv\\Scripts\\python.exe tools\\render_ontology_review.py --check    # exit 1 if the sheet is missing or stale

Exit codes: 0 ok, 1 sheet missing or stale (``--check``), 2 the ontology file is invalid or missing.
The sheet holds no personal data: the sign-off asks for a role code and a date, never a name (AGENTS.md section 5.9).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

from taiji_ai.config import PROJECT_ROOT
from taiji_ai.schemas.ontology import DEFAULT_ONTOLOGY_PATH, Action, Ontology, OntologyError, load_ontology

SHEET_PATH = PROJECT_ROOT.parent / "Docs" / "discovery" / "ontology_review_sheet.md"
DIGEST_LABEL = "Mã đối chiếu với file YAML (SHA-256, 12 ký tự đầu)"
NOT_DETERMINED = "chưa xác định"
SIDE_VI = {"left": "trái", "right": "phải", "none": "không phân biệt"}


def yaml_digest(text: str) -> str:
    """First 12 hex characters of the SHA-256 of ``text`` with CRLF read as LF (Windows checkouts)."""
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()[:12]


def read_sheet_digest(sheet: str) -> str | None:
    """The digest embedded in a sheet, or ``None`` if the sheet carries none."""
    m = re.search(re.escape(DIGEST_LABEL) + r": `([0-9a-f]{12})`", sheet)
    return m.group(1) if m else None


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _sides_vi(sides: tuple[str, ...]) -> str:
    return ", ".join(SIDE_VI.get(s, s) for s in sides)


def _order_cell(action: Action) -> str:
    if action.side_sequence is not None:
        return " → ".join(SIDE_VI.get(s, s) for s in action.side_sequence)
    return NOT_DETERMINED if len(action.sides) > 1 else "—"


def _row(action: Action) -> str:
    names = f"{action.name_zh} / {action.name_vi} / {action.name_en}"
    cells = [action.id, _cell(names), _sides_vi(action.sides), str(action.repetitions), _order_cell(action), "☐", ""]
    return "| " + " | ".join(cells) + " |"


def _status_line(onto: Ontology) -> str:
    form = onto.form
    if form.status == "confirmed":
        return f"đã xác nhận bởi vai trò {form.confirmed_by} ngày {form.confirmed_at}"
    return "chưa xác nhận (bản nháp do agent soạn, cần huấn luyện viên duyệt)"


def _shared_techniques(onto: Ontology) -> str:
    groups: dict[str, list[str]] = {}
    for a in onto.actions:
        groups.setdefault(a.technique, []).append(a.id)
    shared = sorted((ids for ids in groups.values() if len(ids) > 1), key=lambda ids: ids[0])
    return ", ".join("/".join(ids) for ids in shared)


def render_sheet(onto: Ontology, digest: str) -> str:
    """The review sheet (Markdown, LF line ends) for ``onto``; ``digest`` is the digest of its YAML text."""
    undecided = [a.id for a in onto.actions if a.side_sequence is None and len(a.sides) > 1]
    lines = [
        "# Bảng duyệt danh sách 24 thức (ontology v0)",
        "",
        "Bảng này được tạo tự động từ file `taiji_ai/config/ontology_v0.yaml`. Đừng sửa tay: sửa file YAML rồi",
        "chạy lại công cụ `taiji_ai/tools/render_ontology_review.py`.",
        "",
        f"- Trạng thái nội dung: {_status_line(onto)}.",
        f"- {DIGEST_LABEL}: `{digest}`.",
        "- Thời gian dự kiến: khoảng 15 phút. Không cần phỏng vấn; đánh dấu và ghi chú ngắn là đủ.",
        "",
        "## Vì sao cần bảng này",
        "",
        "Danh sách dưới đây là các nhãn mà phần mềm dùng cho mọi đoạn video: thức nào, bên nào, lần thứ mấy.",
        "Nếu nhãn sai thì dữ liệu bị tách nhầm và rất khó sửa về sau. Danh sách do chúng tôi soạn và đối chiếu",
        "với ba trang công khai; chưa có huấn luyện viên nào xác nhận. Tên tiếng Anh và tên Hán-Việt do chúng",
        "tôi viết, chưa đối chiếu với giáo trình tiếng Việt.",
        "",
        "## Cách trả lời",
        "",
        "Với mỗi dòng của bảng 1: nếu đúng thì thay ☐ bằng ☑ ở cột Đúng; nếu chưa đúng thì ghi cách sửa",
        "vào cột Sửa thành.",
        f'Cột Thứ tự bên chỉ là gợi ý tạm. "{NOT_DETERMINED}" nghĩa là chưa có nguồn nào cho biết thứ tự; thức không',
        'phân biệt bên thì ghi "—".',
        "",
        "## Bảng 1. Các thức",
        "",
        "| Mã | Tên (Hán / Việt / Anh) | Bên trong thức | Số lần lặp | Thứ tự bên | Đúng | Sửa thành |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        *[_row(a) for a in onto.actions],
        "",
        "## Bảng 2. Câu hỏi chung",
        "",
        "1. Phiên bản và cách chia. Thầy/cô dạy đúng bản 24 thức này không, và có chia thành đúng 24 thức đánh số như",
        '   bảng 1 không? Ví dụ: "Lãm tước vĩ" trái (A07) và phải (A08) là hai số riêng, còn "Dã mã phân tông" (A02)',
        "   gộp cả trái và phải trong một số.",
        "2. Số lần lặp. Các thức lặp nhiều lần có đúng số lần ở bảng 1 không? Có thầy dạy thức A06 là 3 hoặc 4",
        "   lần, thức A10 là 3 hoặc 4 lần: thầy/cô dạy mấy lần?",
        "3. Thứ tự bên. Với thức lặp xen kẽ trái và phải, lần 1, lần 2, ... là bên nào? Ví dụ A02: trái, phải, trái.",
        f"   Cần điền cho các dòng chưa xác định: {', '.join(undecided) if undecided else 'không còn dòng nào'}.",
        '4. "Bên trái" và "bên phải" nghĩa là gì: chân bước ra trước, tay đang làm động tác, hay hướng xoay người? Một',
        "   đoạn video quay cả thức (ví dụ cả ba lần của A02) thì nên ghi bên nào?",
        "   Quy ước tạm đang dùng (người quản lý dự án chấp thuận, chờ thầy/cô xác nhận):",
        "   bên là chữ trái hoặc phải trong tên chuẩn của thức; với thức tiến bước đó là chân bước ra trước.",
        "   Thầy/cô đồng ý, hay muốn đổi?",
        "5. Không bắt buộc. Có cần chia nhỏ mỗi thức thành các pha (ví dụ chuẩn bị, ra chiêu, thu về) không?",
        "   Một số mô tả công khai có chia nhỏ vài thức, ví dụ thức Lãm tước vĩ.",
        f"6. Không bắt buộc. Các số cùng một kỹ thuật ({_shared_techniques(onto) or 'không có'}): khi so sánh,",
        "   có được lấy mẫu của số này làm chuẩn cho số kia không?",
        "",
        "## Xác nhận",
        "",
        "- Mã vai trò của người duyệt (ví dụ H1; không ghi tên):",
        "- Ngày duyệt (YYYY-MM-DD):",
        "- Kết luận: ☐ đúng như bảng 1 ☐ đúng sau khi sửa như đã ghi",
        "",
        "Sau khi nhận lại bảng này, người quản lý dự án cập nhật file YAML theo các sửa đổi, rồi đặt",
        "`status: confirmed`, `confirmed_by` và `confirmed_at`, và chạy lại công cụ. Không ghi tên thật hay",
        "thông tin cá nhân vào bảng.",
        "",
    ]
    return "\n".join(lines)


def _read_lf(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the coach review sheet of the ontology.")
    parser.add_argument("--ontology", type=Path, default=DEFAULT_ONTOLOGY_PATH, help="ontology YAML file")
    parser.add_argument("--out", type=Path, default=SHEET_PATH, help="sheet to write or check")
    parser.add_argument("--check", action="store_true", help="exit 1 if the sheet is missing or differs; write nothing")
    args = parser.parse_args(argv)

    try:
        onto = load_ontology(args.ontology)
    except (OntologyError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    sheet = render_sheet(onto, yaml_digest(_read_lf(args.ontology)))

    if args.check:
        if not args.out.exists():
            print("sheet is missing; run the tool without --check", file=sys.stderr)
            return 1
        if _read_lf(args.out) != sheet:
            print("sheet is stale; run the tool without --check", file=sys.stderr)
            return 1
        print("sheet is up to date")
        return 0

    _write_atomic(args.out, sheet)
    print("sheet written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
