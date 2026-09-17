"""Build a Word report from Markdown in the team's Document Format Standard.

    python tools/build_report.py "docs/weekly-reports/Week 2 Progress Report.md"

Writes the .docx beside the .md. What the standard asks for, and where it is done:

- Times New Roman 12, line spacing 1.5, justified body text       (_configure)
- Numbered, bold headings in Word's Heading styles, each main
  section on a new page                                            (_configure)
- Title page with no page number; roman numerals (ii, iii, ...)
  on the front matter; arabic numbering restarting at 1 from the
  first numbered section                                           (_sections)
- Generated table of contents, list of tables, list of figures     (_field)
- Table captions above tables, numbered by a SEQ field             (_table)

On Windows with Word installed, the fields are then updated through Word so the
contents pages are filled in when the file is opened. Elsewhere they fill in
when the reader presses F9 or prints.

Markdown conventions understood here:

    ---                       title block: title, subtitle, then one line each
    title: ...
    subtitle: ...
    line: ...
    ---
    # Declaration             unnumbered heading: front matter
    [[TOC]]  [[TABLES]]  [[FIGURES]]
    # 1. Introduction         the first numbered heading starts page 1
    ## 1.1 Scope
    <!-- Table: caption -->   caption for the table directly below
    | a | b |
    - bullet, 1. numbered item, **bold**, *italic*
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

FONT = "Times New Roman"
BODY_SIZE = Pt(12)
TABLE_SIZE = Pt(10)
LINE_SPACING = 1.5
HEADING_SIZES = {1: Pt(16), 2: Pt(14), 3: Pt(13)}
NUMBERED = re.compile(r"^\d+(\.\d+)*\.?\s")
INLINE = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*)")

PLACEHOLDERS = {
    "[[TOC]]": ("Table of Contents", 'TOC \\o "1-3" \\h \\z \\u', None),
    "[[TABLES]]": ("List of Tables", 'TOC \\h \\z \\c "Table"', None),
    "[[FIGURES]]": ("List of Figures", 'TOC \\h \\z \\c "Figure"', "No figures are included in this report."),
}


def _fonts(style_or_run, size: Optional[Pt] = None) -> None:
    font = style_or_run.font
    font.name = FONT
    rpr = style_or_run.element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    for attribute in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(attribute), FONT)
    for theme in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        fonts.attrib.pop(qn(theme), None)
    if size is not None:
        font.size = size


def _configure(document) -> None:
    normal = document.styles["Normal"]
    _fonts(normal, BODY_SIZE)
    normal.paragraph_format.line_spacing = LINE_SPACING
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for level, size in HEADING_SIZES.items():
        style = document.styles[f"Heading {level}"]
        _fonts(style, size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        style.paragraph_format.space_before = Pt(12)
        style.paragraph_format.space_after = Pt(6)
        style.paragraph_format.line_spacing = LINE_SPACING
    document.styles["Heading 1"].paragraph_format.page_break_before = True
    for name in ("List Bullet", "List Number", "Caption"):
        style = document.styles[name]
        _fonts(style, BODY_SIZE if name != "Caption" else Pt(11))
        style.paragraph_format.line_spacing = LINE_SPACING
    from docx.enum.style import WD_STYLE_TYPE

    # Headings of the contents pages themselves. Styled like Heading 1 but kept
    # out of the table of contents, which should not list itself.
    contents = document.styles.add_style("Contents Heading", WD_STYLE_TYPE.PARAGRAPH)
    contents.base_style = normal
    _fonts(contents, HEADING_SIZES[1])
    contents.font.bold = True
    contents.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    contents.paragraph_format.page_break_before = True
    contents.paragraph_format.space_after = Pt(6)
    caption = document.styles["Caption"]
    caption.font.color.rgb = RGBColor(0, 0, 0)
    caption.font.italic = False
    caption.paragraph_format.keep_with_next = True
    section = document.sections[0]
    section.left_margin = section.right_margin = Inches(1)
    section.top_margin = section.bottom_margin = Inches(1)


def _field(paragraph, instruction: str, placeholder: str = "") -> None:
    run = paragraph.add_run()
    for kind, text in (("begin", None), ("instr", instruction), ("separate", None), ("text", placeholder), ("end", None)):
        if kind == "instr":
            element = OxmlElement("w:instrText")
            element.set(qn("xml:space"), "preserve")
            element.text = f" {text} "
        elif kind == "text":
            element = OxmlElement("w:t")
            element.text = text
        else:
            element = OxmlElement("w:fldChar")
            element.set(qn("w:fldCharType"), kind)
        run._r.append(element)


def _page_numbering(section, fmt: str, start: int) -> None:
    properties = section._sectPr
    numbering = properties.find(qn("w:pgNumType"))
    if numbering is None:
        numbering = OxmlElement("w:pgNumType")
        properties.append(numbering)
    numbering.set(qn("w:fmt"), fmt)
    numbering.set(qn("w:start"), str(start))


def _footer_page_number(section) -> None:
    section.footer.is_linked_to_previous = False
    paragraph = section.footer.paragraphs[0]
    paragraph.text = ""
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _field(paragraph, "PAGE", "1")
    for run in paragraph.runs:
        _fonts(run, Pt(11))


def _runs(paragraph, text: str) -> None:
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("*"):
            run = paragraph.add_run(part[1:-1])
            run.italic = True
        else:
            run = paragraph.add_run(part)
        _fonts(run)


def _table(document, rows: List[List[str]], caption: str) -> None:
    paragraph = document.add_paragraph(style="Caption")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    label = paragraph.add_run("Table ")
    label.bold = True
    _field(paragraph, "SEQ Table \\* ARABIC", "1")
    paragraph.runs[-1].bold = True
    paragraph.add_run(": ").bold = True
    paragraph.add_run(caption)
    for run in paragraph.runs:
        _fonts(run)

    table = document.add_table(rows=0, cols=len(rows[0]))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for index, row in enumerate(rows):
        cells = table.add_row().cells
        for cell, value in zip(cells, row):
            cell.text = ""
            cell_paragraph = cell.paragraphs[0]
            cell_paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            cell_paragraph.paragraph_format.line_spacing = 1.0
            cell_paragraph.paragraph_format.space_after = Pt(2)
            _runs(cell_paragraph, value)
            for run in cell_paragraph.runs:
                run.font.size = TABLE_SIZE
                run.bold = run.bold or index == 0
        if index == 0:
            header = table.rows[0]._tr.get_or_add_trPr()
            repeat = OxmlElement("w:tblHeader")
            repeat.set(qn("w:val"), "true")
            header.append(repeat)
    document.add_paragraph().paragraph_format.space_after = Pt(0)


def _title_page(document, block: dict) -> None:
    for _ in range(6):
        document.add_paragraph()
    for text, size, bold in ((block.get("title", ""), Pt(20), True), (block.get("subtitle", ""), Pt(14), False)):
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run(text)
        run.bold = bold
        _fonts(run, size)
    document.add_paragraph()
    for line in block.get("lines", []):
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _runs(paragraph, line)


def _parse_title(lines: List[str]) -> Tuple[dict, List[str]]:
    if not lines or lines[0].strip() != "---":
        return {}, lines
    block: dict = {"lines": []}
    end = lines.index("---", 1)
    for line in lines[1:end]:
        key, _, value = line.partition(":")
        if key.strip() == "line":
            block["lines"].append(value.strip())
        else:
            block[key.strip()] = value.strip()
    return block, lines[end + 1 :]


def build(source: Path, destination: Path) -> Path:
    title, lines = _parse_title(source.read_text(encoding="utf-8").splitlines())
    document = Document()
    _configure(document)
    first = document.sections[0]
    first.different_first_page_header_footer = True
    _page_numbering(first, "lowerRoman", 1)
    _footer_page_number(first)
    if title:
        _title_page(document, title)

    body_started = False
    caption = ""
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()
        if stripped.startswith("<!--") and "Table:" in stripped:
            caption = stripped.split("Table:", 1)[1].replace("-->", "").strip()
        elif stripped.startswith("|"):
            block: List[List[str]] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                cells = [c.strip() for c in lines[index].strip().strip("|").split("|")]
                if not all(set(c) <= set("-: ") for c in cells):
                    block.append(cells)
                index += 1
            _table(document, block, caption)
            caption = ""
            continue
        elif stripped in PLACEHOLDERS:
            heading, instruction, note = PLACEHOLDERS[stripped]
            document.add_paragraph(heading, style="Contents Heading")
            if note:
                _runs(document.add_paragraph(), note)
            else:
                _field(document.add_paragraph(), instruction, "Right-click and choose Update Field.")
        elif stripped.startswith("#"):
            level = min(len(stripped) - len(stripped.lstrip("#")), 3)
            text = stripped.lstrip("#").strip()
            if level == 1 and NUMBERED.match(text) and not body_started:
                body = document.add_section(WD_SECTION.NEW_PAGE)
                body.different_first_page_header_footer = False
                _page_numbering(body, "decimal", 1)
                _footer_page_number(body)
                body_started = True
                heading = document.add_heading(text, level=1)
                heading.paragraph_format.page_break_before = False
            else:
                document.add_heading(text, level=level)
        elif re.match(r"^[-*]\s+", stripped):
            _runs(document.add_paragraph(style="List Bullet"), re.sub(r"^[-*]\s+", "", stripped))
        elif re.match(r"^\d+\.\s+", stripped):
            _runs(document.add_paragraph(style="List Number"), re.sub(r"^\d+\.\s+", "", stripped))
        elif stripped:
            _runs(document.add_paragraph(), stripped)
        index += 1

    document.save(str(destination))
    _update_fields_with_word(destination)
    return destination


def _update_fields_with_word(path: Path) -> None:
    """Fill the contents pages through Word, when Word is available.

    Word cannot open paths over 255 characters, so the file is updated in a
    short temporary folder and copied back.
    """
    if sys.platform != "win32":
        return
    with tempfile.TemporaryDirectory(prefix="rpt") as folder:
        working = Path(folder) / "report.docx"
        shutil.copyfile(path, working)
        script = (
            "$w = New-Object -ComObject Word.Application; $w.Visible = $false; "
            f"try {{ $d = $w.Documents.Open('{working}'); "
            # Caption numbers (SEQ) first, then the contents lists built from
            # them. The list of tables lives in TablesOfFigures, not
            # TablesOfContents.
            "$d.Fields.Update() | Out-Null; "
            "foreach ($t in $d.TablesOfContents) { $t.Update() | Out-Null }; "
            "foreach ($t in $d.TablesOfFigures) { $t.Update() | Out-Null }; "
            "$d.Save(); $d.Close() } finally { $w.Quit() }"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=180
        )
        if result.returncode == 0:
            shutil.copyfile(working, path)
        else:
            print(f"Fields not updated (press F9 in Word): {result.stderr.strip()[:200]}", file=sys.stderr)


def main(argv: List[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 1
    source = Path(argv[0])
    destination = build(source, source.with_suffix(".docx"))
    print(f"Wrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
