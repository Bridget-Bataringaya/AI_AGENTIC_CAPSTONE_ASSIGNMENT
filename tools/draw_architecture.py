"""Draw the as-built architecture of ProcureCheck as a PNG.

    python tools/draw_architecture.py

Writes docs/architecture/as-built-architecture.png. Drawn with PyMuPDF, which
the application already depends on, so no drawing package is needed. Every box
names the module that implements it, so the figure can be checked against the
code.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Tuple

import pymupdf

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = REPO_ROOT / "docs" / "architecture" / "as-built-architecture.png"
WIDTH, HEIGHT = 980, 640
INK = (0.12, 0.12, 0.14)
LINE = (0.30, 0.30, 0.34)
FILLS = {
    "people": (0.93, 0.94, 0.97),
    "app": (1.00, 1.00, 1.00),
    "control": (0.95, 0.97, 0.94),
    "tool": (0.97, 0.96, 0.92),
    "store": (0.95, 0.95, 0.95),
    "model": (0.92, 0.95, 0.98),
}
Box = Tuple[float, float, float, float]


def box(page, rect: Box, title: str, body: str = "", kind: str = "app", dashed: bool = False) -> Box:
    r = pymupdf.Rect(*rect)
    shape = page.new_shape()
    shape.draw_rect(r)
    shape.finish(color=LINE, fill=FILLS[kind], width=1.0, dashes="[4 3] 0" if dashed else None)
    shape.commit()
    inner = pymupdf.Rect(r.x0 + 5, r.y0 + 4, r.x1 - 5, r.y1 - 3)
    text = title if not body else f"{title}\n{body}"
    size = 8.6
    while page.insert_textbox(inner, text, fontsize=size, fontname="helv", color=INK, align=1) < 0 and size > 6:
        size -= 0.3
        page.draw_rect(inner, color=FILLS[kind], fill=FILLS[kind], width=0)
    return rect


def arrow(page, start: Tuple[float, float], end: Tuple[float, float], label: str = "", dashed: bool = False) -> None:
    a, b = pymupdf.Point(*start), pymupdf.Point(*end)
    shape = page.new_shape()
    shape.draw_line(a, b)
    shape.finish(color=LINE, width=1.0, dashes="[3 2] 0" if dashed else None)
    direction = b - a
    length = abs(direction) or 1.0
    unit = pymupdf.Point(direction.x / length, direction.y / length)
    normal = pymupdf.Point(-unit.y, unit.x)
    tip = b
    base = b - unit * 7
    shape.draw_polyline([base + normal * 3.2, tip, base - normal * 3.2, base + normal * 3.2])
    shape.finish(color=LINE, fill=LINE, width=0.5, closePath=True)
    shape.commit()
    if label:
        middle = a + direction * 0.5
        page.insert_text(pymupdf.Point(middle.x - (14 if abs(direction.y) < 1 else -4), middle.y - (6 if abs(direction.y) < 1 else 3)), label, fontsize=7.2, fontname="helv", color=INK)


def bottom(r: Box) -> Tuple[float, float]:
    return ((r[0] + r[2]) / 2, r[3])


def top(r: Box) -> Tuple[float, float]:
    return ((r[0] + r[2]) / 2, r[1])


def draw() -> Path:
    document = pymupdf.open()
    page = document.new_page(width=WIDTH, height=HEIGHT)
    page.draw_rect(page.rect, color=(1, 1, 1), fill=(1, 1, 1))

    # People
    officer = box(page, (40, 18, 300, 62), "Procurement officer", "CLI on the officer's machine, or API with an X-API-Key", "people")
    committee = box(page, (330, 18, 560, 62), "Evaluation committee", "May only generate and read reports", "people")
    bidder = box(page, (590, 18, 760, 62), "Bidder or guest", "Refused: no permissions", "people")

    # Entry and the two gates in front of the work
    entry = box(page, (40, 92, 760, 128), "Entry points: run.py (CLI) and api.py (FastAPI)",
                "Roles from API keys; legacy routes guarded by legacy_auth_patch.py", "app")
    guard = box(page, (40, 152, 300, 200), "Safety guard (safety.py)",
                "Refuses requests to score, rank, give a legal view or recommend an award", "control")
    ingest = box(page, (330, 152, 560, 200), "Ingestion (ingestion/)",
                 "PDF, DOCX or TXT to pages marked [PAGE n]; one submission per run", "app")
    checklist = box(page, (590, 152, 760, 200), "Checklist", "A named file, or the bundled 22-item template", "app")

    # Orchestration and the executor
    workflow = box(page, (40, 228, 330, 290), "Workflow (workflow/): direct orchestration",
                   "Sense, plan, act, observe. At most 7 iterations, 1 retry after an outage, 1 re-check round. "
                   "Every stop hands the case to an officer.", "app")
    executor = box(page, (400, 228, 760, 290), "Tool executor (tools/registry.py)",
                   "In order: the tool exists, the caller may use it, the arguments match, a person approves "
                   "if needed, the answer matches its schema", "control")

    # Tools
    check = box(page, (40, 322, 230, 372), "check_document_completeness", "Runs the matching engine", "tool")
    report = box(page, (250, 322, 420, 372), "generate_completeness_report", "Arithmetic only, no model", "tool")
    ticket = box(page, (440, 322, 590, 372), "create_review_ticket", "Draft for each Unclear item", "tool")
    publish = box(page, (610, 322, 760, 372), "publish_completeness_report", "Higher-impact action", "tool")

    engine = box(page, (40, 400, 420, 486), "Matching engine (engine.py, prompts.py)",
                 "1. First pass, one call per item, the whole submission in the prompt.\n"
                 "2. Code guards: quotation in the submission, page exists, confidence at least 0.85.\n"
                 "3. Evidence check: a second call shown only the requirement and the quotation.", "app")
    approval = box(page, (610, 400, 760, 450), "Approval gate (tools/approval.py)",
                   "An officer's sign-off at an interactive terminal", "control")
    record = box(page, (610, 474, 760, 516), "Procurement record", "Simulated, append-only", "store")
    queue = box(page, (440, 400, 590, 450), "Review queue", "Session only", "store")

    model = box(page, (40, 530, 420, 580), "Ollama on localhost: llama3.1:8b",
                "Temperature 0, JSON constrained to the schema, 16,384-token context, no cloud call", "model")

    # Side stores and outputs
    memory = box(page, (790, 92, 960, 168), "Case history (memory/)",
                 "SQLite, item statuses only, 180 days. Recalled before the loop, compared after it.", "store")
    logs = box(page, (790, 186, 960, 262), "Run log (observability/)",
                "JSON Lines: calls, sizes, timings, outcomes. No document text. 90 days.", "store")
    outputs = box(page, (790, 280, 960, 356), "Outputs",
                   "PDF report of record, Word copy, trace JSON, hand-off to the officer", "store")
    search = box(page, (790, 400, 960, 500), "Corpus search (retrieval/)",
                 "Separate index and search commands. BM25 plus nomic-embed-text over 35 documents. "
                 "Not used by the check.", "store", dashed=True)

    arrow(page, bottom(officer), (bottom(officer)[0], entry[1]))
    arrow(page, bottom(committee), (bottom(committee)[0], entry[1]))
    arrow(page, bottom(bidder), (bottom(bidder)[0], entry[1]), "refused", dashed=True)
    arrow(page, (bottom(guard)[0], entry[3]), top(guard))
    arrow(page, (bottom(ingest)[0], entry[3]), top(ingest))
    arrow(page, (bottom(checklist)[0], entry[3]), top(checklist))
    arrow(page, (170, guard[3]), (170, workflow[1]), "allowed")
    arrow(page, (445, ingest[3]), (300, workflow[1]))
    arrow(page, (675, checklist[3]), (680, executor[1]))
    arrow(page, (workflow[2], 259), (executor[0], 259), "tool calls")
    for start_x, target in ((410, check), (450, report), (515, ticket), (685, publish)):
        arrow(page, (start_x, executor[3]), top(target))
    arrow(page, bottom(check), (135, engine[1]))
    arrow(page, bottom(ticket), top(queue))
    arrow(page, bottom(publish), top(approval))
    arrow(page, bottom(approval), top(record), "approved")
    arrow(page, (230, engine[3]), (230, model[1]), "per item")
    arrow(page, (executor[2], 250), (memory[0], 140), dashed=True)
    arrow(page, (executor[2], 262), (logs[0], 224), dashed=True)
    arrow(page, (executor[2], 276), (outputs[0], 318), dashed=True)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    page.get_pixmap(dpi=220).save(str(OUTPUT))
    document.close()
    return OUTPUT


if __name__ == "__main__":
    print(f"Wrote {draw()}", file=sys.stderr)
