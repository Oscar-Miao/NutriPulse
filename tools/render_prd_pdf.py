"""Render the NutriPulse Markdown PRD as a Chinese-friendly A4 PDF.

Usage: python tools/render_prd_pdf.py INPUT.md OUTPUT.pdf
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

import mistune
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


GREEN = colors.HexColor("#2ECC71")
INK = colors.HexColor("#172B3A")
MUTED = colors.HexColor("#526675")
PALE = colors.HexColor("#EAF8F0")
PAPER = colors.HexColor("#F8F9FA")


def inline(nodes: list[dict]) -> str:
    chunks: list[str] = []
    for node in nodes:
        kind = node["type"]
        if kind == "text":
            chunks.append(html.escape(node.get("raw", "")))
        elif kind == "codespan":
            chunks.append(f'<font color="#006C49">{html.escape(node.get("raw", ""))}</font>')
        elif kind == "strong":
            chunks.append(f'<b>{inline(node.get("children", []))}</b>')
        elif kind == "emphasis":
            chunks.append(f'<i>{inline(node.get("children", []))}</i>')
        elif kind == "link":
            chunks.append(inline(node.get("children", [])))
        elif kind in {"softbreak", "linebreak"}:
            chunks.append("<br/>")
        elif kind == "image":
            chunks.append(inline(node.get("children", [])))
        else:
            chunks.append(inline(node.get("children", [])))
    return "".join(chunks)


def main(source: Path, target: Path) -> None:
    font_path = Path(r"C:\Windows\Fonts\simhei.ttf")
    pdfmetrics.registerFont(TTFont("PRDChinese", str(font_path)))
    pdfmetrics.registerFontFamily("PRDChinese", normal="PRDChinese", bold="PRDChinese")
    body = ParagraphStyle(
        "body", fontName="PRDChinese", fontSize=8.5, leading=14,
        textColor=INK, spaceAfter=5, wordWrap="CJK", allowWidows=0,
        allowOrphans=0,
    )
    heading = {
        1: ParagraphStyle("h1", parent=body, fontSize=20, leading=27,
                          textColor=INK, spaceBefore=11, spaceAfter=15, keepWithNext=True),
        2: ParagraphStyle("h2", parent=body, fontSize=13, leading=19,
                          textColor=GREEN, spaceBefore=17, spaceAfter=8, keepWithNext=True),
        3: ParagraphStyle("h3", parent=body, fontSize=10, leading=16,
                          textColor=INK, spaceBefore=12, spaceAfter=6, keepWithNext=True),
        4: ParagraphStyle("h4", parent=body, fontSize=9, leading=14,
                          textColor=INK, spaceBefore=10, spaceAfter=5, keepWithNext=True),
    }
    cell = ParagraphStyle("cell", parent=body, fontSize=6.7, leading=10,
                          spaceAfter=0, splitLongWords=True)
    cell_head = ParagraphStyle("cell-head", parent=cell, textColor=colors.white)
    quote = ParagraphStyle("quote", parent=body, textColor=MUTED, leftIndent=12,
                            borderColor=GREEN, borderWidth=2, borderPadding=8)
    code = ParagraphStyle("code", parent=body, fontSize=6.7, leading=9.5,
                           backColor=PAPER, borderPadding=8, textColor=INK)

    parser = mistune.create_markdown(renderer="ast", plugins=["table", "strikethrough"])
    tree = parser(source.read_text(encoding="utf-8"))
    story = []

    def render(node: dict):
        kind = node["type"]
        if kind == "heading":
            level = min(node["attrs"]["level"], 4)
            return Paragraph(inline(node["children"]), heading[level])
        if kind in {"paragraph", "block_text"}:
            return Paragraph(inline(node["children"]), body)
        if kind == "thematic_break":
            return HRFlowable(width="100%", thickness=0.45, color=colors.HexColor("#DAE4E1"),
                              spaceBefore=5, spaceAfter=9)
        if kind == "table":
            rows = []
            head = node["children"][0]
            rows.append([Paragraph(inline(c.get("children", [])), cell_head)
                         for c in head.get("children", [])])
            for row in node["children"][1].get("children", []):
                rows.append([Paragraph(inline(c.get("children", [])), cell)
                             for c in row.get("children", [])])
            count = len(rows[0])
            width = 507 / count
            table = Table(rows, colWidths=[width] * count, repeatRows=1,
                          hAlign="LEFT", splitByRow=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#257E5C")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PAPER]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, -1), (-1, -1), 0.3, colors.HexColor("#D8E4DF")),
            ]))
            return table
        if kind == "list":
            ordered = node.get("attrs", {}).get("ordered", False)
            items = []
            for item in node.get("children", []):
                rendered = [render(c) for c in item.get("children", [])]
                rendered = [r for r in rendered if r is not None]
                if rendered:
                    items.append(ListItem(rendered, leftIndent=10))
            return ListFlowable(items, bulletType="1" if ordered else "bullet",
                                start=str(node.get("attrs", {}).get("start", 1)) if ordered else "-",
                                leftIndent=20, bulletFontName="PRDChinese",
                                bulletFontSize=7)
        if kind == "block_quote":
            content = " ".join(inline(c.get("children", [])) for c in node.get("children", []))
            return Paragraph(content, quote)
        if kind == "block_code":
            lines = node.get("raw", "").strip("\n").splitlines()
            # Wrap diagrams and JSON without truncating the right edge.
            wrapped = []
            for line in lines:
                wrapped.extend(simpleSplit(line, "PRDChinese", 6.7, 490) or [""])
            return Preformatted("\n".join(wrapped), code, maxLineLength=100)
        return None

    for node in tree:
        if node["type"] == "blank_line":
            continue
        flowable = render(node)
        if flowable is not None:
            story.append(flowable)
            if node["type"] in {"table", "list", "block_code"}:
                story.append(Spacer(1, 7))

    target.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(target), pagesize=(595.276, 841.89),
        leftMargin=44, rightMargin=44, topMargin=50, bottomMargin=45,
        title="NutriPulse 健身饮食一体化 App 产品需求文档",
        author="Codex", subject="产品需求、系统设计、数据库与测试方案",
    )

    def decorate(canvas, pdf_doc):
        canvas.saveState()
        canvas.setStrokeColor(GREEN)
        canvas.setLineWidth(1.4)
        canvas.line(44, 818, 551, 818)
        canvas.setFont("PRDChinese", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(44, 827, "NutriPulse 产品需求文档  |  V1.1")
        canvas.drawRightString(551, 25, f"{pdf_doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: render_prd_pdf.py INPUT.md OUTPUT.pdf")
    main(Path(sys.argv[1]), Path(sys.argv[2]))
