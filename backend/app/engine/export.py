"""
engine/export.py
----------------
Excel and PDF export.

Excel:  fully implemented using openpyxl via pandas ExcelWriter.
PDF:    scaffold using reportlab; will be expanded in Phase 4.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Excel formatting helpers
# ---------------------------------------------------------------------------

def _format_data_sheet(ws: Any) -> None:
    """
    Apply standard formatting to a data worksheet:
    - bold + coloured header with thin border
    - frozen top row + auto-filter
    - auto-sized columns
    - 2-decimal float formatting
    - thin borders on all data cells
    - alternate row shading for readability
    """
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    HEADER_BG         = "E8EAF6"
    HEADER_FONT_COLOR = "1A237E"
    ROW_ALT_BG        = "F8F9FF"

    header_fill = PatternFill(start_color=HEADER_BG, end_color=HEADER_BG, fill_type="solid")
    alt_fill    = PatternFill(start_color=ROW_ALT_BG, end_color=ROW_ALT_BG, fill_type="solid")
    header_font = Font(bold=True, color=HEADER_FONT_COLOR, size=11)

    thin   = Side(style="thin", color="D1D5DB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    max_row = ws.max_row
    max_col = ws.max_column

    for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=max_row), start=1):
        for cell in row:
            cell.border = border
            if row_idx == 1:
                cell.font      = header_font
                cell.fill      = header_fill
                cell.alignment = Alignment(horizontal="left", vertical="center")
            else:
                if row_idx % 2 == 0:
                    cell.fill = alt_fill
                if isinstance(cell.value, float):
                    cell.number_format = "0.00"
                cell.alignment = Alignment(vertical="center")

    ws.freeze_panes = "A2"

    if max_row > 1 and max_col > 0:
        ws.auto_filter.ref = ws.dimensions

    ws.row_dimensions[1].height = 20

    for col in ws.columns:
        max_len    = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                val     = str(cell.value) if cell.value is not None else ""
                max_len = max(max_len, len(val))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 50)


def _write_report_summary_sheet(wb: Any, metadata: Dict[str, Any]) -> None:
    """
    Write a polished 'Report Summary' executive-summary sheet at position 0.
    Layout:
      Row 1   : merged title bar (dark indigo bg, large white text)
      Spacer
      Section : "Report Information"
      Rows    : metadata table (Query, Generated, Dataset 1, Dataset 2)
      Spacer
      Section : "Analysis Summary"
      Row     : summary text (wrapped)
      Spacer
      Section : "Key Finding"
      Row     : first sentence of summary
    """
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    ws = wb.create_sheet("Report Summary")

    # ── Styles ────────────────────────────────────────────────────────────────
    TITLE_BG    = PatternFill(start_color="3730A3", end_color="3730A3", fill_type="solid")
    SECTION_BG  = PatternFill(start_color="EEF2FF", end_color="EEF2FF", fill_type="solid")
    LABEL_BG    = PatternFill(start_color="F5F5F5", end_color="F5F5F5", fill_type="solid")

    TITLE_FONT   = Font(bold=True, size=18, color="FFFFFF")
    SECTION_FONT = Font(bold=True, size=12, color="3730A3")
    LABEL_FONT   = Font(bold=True, size=11, color="374151")
    VALUE_FONT   = Font(size=11, color="111827")

    WRAP    = Alignment(wrap_text=True, vertical="top",    horizontal="left")
    CENTER  = Alignment(horizontal="center", vertical="center")
    LEFT    = Alignment(horizontal="left",   vertical="center")

    thin_side   = Side(style="thin", color="D1D5DB")
    thin_border = Border(
        left=thin_side, right=thin_side, top=thin_side, bottom=thin_side
    )

    def _section_row(label: str, span: str, row_n: int) -> None:
        ws.append([label, "", "", "", ""])
        ws.merge_cells(span)
        ws[f"A{row_n}"].font      = SECTION_FONT
        ws[f"A{row_n}"].fill      = SECTION_BG
        ws[f"A{row_n}"].alignment = LEFT
        ws.row_dimensions[row_n].height = 22

    def _meta_row(label: str, value: str) -> None:
        ws.append(["", label, value, "", ""])
        r  = ws.max_row
        lc = ws.cell(r, 2)
        vc = ws.cell(r, 3)
        ws.merge_cells(f"C{r}:E{r}")
        lc.font      = LABEL_FONT
        lc.fill      = LABEL_BG
        lc.border    = thin_border
        lc.alignment = LEFT
        vc.font      = VALUE_FONT
        vc.border    = thin_border
        vc.alignment = WRAP
        # Taller rows for the Query field (can be long)
        _val_len = len(str(value)) if value else 0
        ws.row_dimensions[r].height = max(24, min(60, _val_len // 3 + 18))

    # ── Row 1: Title bar ──────────────────────────────────────────────────────
    ws.append(["Faculty Analytics Report", "", "", "", ""])
    ws.merge_cells("A1:E1")
    ws["A1"].font      = TITLE_FONT
    ws["A1"].fill      = TITLE_BG
    ws["A1"].alignment = CENTER
    ws.row_dimensions[1].height = 48

    # ── Row 2: Spacer ─────────────────────────────────────────────────────────
    ws.append([""])
    ws.row_dimensions[2].height = 8

    # ── Row 3: Section header ─────────────────────────────────────────────────
    _section_row("Report Information", "A3:E3", 3)

    # ── Metadata rows ─────────────────────────────────────────────────────────
    _meta_row("Query",      metadata.get("question", "—"))
    _meta_row("Generated",  metadata.get("generated_at", "—"))

    # Use cleaner dataset labels (no "File 1 / Term 1" framing)
    label_a = metadata.get("label_a")
    label_b = metadata.get("label_b")
    if label_a:
        _meta_row("Dataset 1",  label_a)
    if label_b:
        _meta_row("Dataset 2",  label_b)

    # ── Spacer ────────────────────────────────────────────────────────────────
    ws.append([""])
    ws.row_dimensions[ws.max_row].height = 8

    # ── Analysis Summary section ──────────────────────────────────────────────
    sr = ws.max_row + 1
    _section_row("Analysis Summary", f"A{sr}:E{sr}", sr)

    summary_text = metadata.get("summary", "")
    ws.append(["", summary_text, "", "", ""])
    tr = ws.max_row
    ws.merge_cells(f"B{tr}:E{tr}")
    ws.cell(tr, 2).font      = VALUE_FONT
    ws.cell(tr, 2).alignment = WRAP
    ws.cell(tr, 2).border    = thin_border
    # Height: ~18pt per line, estimate 60 chars per line in the column width
    _lines = max(2, (len(summary_text) // 60) + 1)
    ws.row_dimensions[tr].height = max(54, _lines * 20)

    # ── Spacer ────────────────────────────────────────────────────────────────
    ws.append([""])
    ws.row_dimensions[ws.max_row].height = 10

    # ── Key Finding section ───────────────────────────────────────────────────
    kf_row = ws.max_row + 1
    _section_row("Key Finding", f"A{kf_row}:E{kf_row}", kf_row)

    # First meaningful sentence of the summary
    key_finding = summary_text.split(".")[0].strip() + "." if summary_text else "—"
    ws.append(["", key_finding, "", "", ""])
    kr = ws.max_row
    ws.merge_cells(f"B{kr}:E{kr}")
    ws.cell(kr, 2).font      = Font(bold=True, size=12, color="1e1b4b")
    ws.cell(kr, 2).alignment = WRAP
    ws.cell(kr, 2).border    = thin_border
    _kf_lines = max(2, (len(key_finding) // 60) + 1)
    ws.row_dimensions[kr].height = max(40, _kf_lines * 20)

    # ── Data Quality Notes section ────────────────────────────────────────────
    dq_notes = metadata.get("data_quality_notes", [])
    if dq_notes:
        ws.append([""])
        ws.row_dimensions[ws.max_row].height = 8

        dq_hdr_row = ws.max_row + 1
        _section_row("Data Quality Notes", f"A{dq_hdr_row}:E{dq_hdr_row}", dq_hdr_row)

        OK_FILL   = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
        WARN_FILL = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid")
        OK_FONT   = Font(size=11, color="065F46")
        WARN_FONT = Font(size=11, color="92400E")

        for note in dq_notes:
            level   = note.get("level", "ok")
            message = note.get("message", "")
            prefix  = "✓  " if level == "ok" else "⚠  "
            ws.append(["", prefix + message, "", "", ""])
            nr = ws.max_row
            ws.merge_cells(f"B{nr}:E{nr}")
            ws.cell(nr, 2).fill      = OK_FILL if level == "ok" else WARN_FILL
            ws.cell(nr, 2).font      = OK_FONT if level == "ok" else WARN_FONT
            ws.cell(nr, 2).alignment = WRAP
            ws.cell(nr, 2).border    = thin_border
            ws.row_dimensions[nr].height = max(24, (len(message) // 60 + 1) * 16)

    # ── Column widths ─────────────────────────────────────────────────────────
    ws.column_dimensions["A"].width = 2     # left gutter
    ws.column_dimensions["B"].width = 22    # labels
    ws.column_dimensions["C"].width = 55    # primary value
    ws.column_dimensions["D"].width = 10    # value overflow
    ws.column_dimensions["E"].width = 10

    # Move to sheet position 0
    wb.move_sheet(ws, offset=-(len(wb.sheetnames) - 1))


def _write_charts_sheet(wb: Any, charts: List[Any]) -> None:
    """
    Create a 'Charts' sheet and embed each chart as an image.
    Requires Pillow (already in requirements.txt).
    """
    if not charts:
        return

    import base64
    from io import BytesIO

    try:
        from openpyxl.drawing.image import Image as XLImage
    except ImportError:
        return  # openpyxl image support unavailable

    from openpyxl.styles import Alignment, Font, PatternFill

    ws = wb.create_sheet("Charts")

    # Sheet title row
    ws.append(["Charts", "", "", "", "", "", "", ""])
    ws.merge_cells("A1:H1")
    ws["A1"].font      = Font(bold=True, size=14, color="3730A3")
    ws["A1"].fill      = PatternFill(start_color="EEF2FF", end_color="EEF2FF", fill_type="solid")
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 28

    # Display dimensions for each chart in Excel (pixels)
    IMG_W = 740
    IMG_H = 480
    # Rows needed: Excel default row = 15pt ≈ 20px; add buffer for title + spacing
    ROWS_PER_IMG = int(IMG_H / 18) + 6  # ~33 rows

    current_row = 3

    for chart in charts:
        img_b64 = getattr(chart, "image_b64", None)
        title   = getattr(chart, "title", "Chart")
        if not img_b64:
            continue
        try:
            # Title label row
            ws.cell(current_row, 1).value     = title
            ws.cell(current_row, 1).font      = Font(bold=True, size=11, color="1A237E")
            ws.cell(current_row, 1).fill      = PatternFill(
                start_color="EEF2FF", end_color="EEF2FF", fill_type="solid"
            )
            ws.cell(current_row, 1).alignment = Alignment(horizontal="left", vertical="center")
            ws.row_dimensions[current_row].height = 22

            # Image row
            anchor_row = current_row + 1
            xl_img        = XLImage(BytesIO(base64.b64decode(img_b64)))
            xl_img.width  = IMG_W
            xl_img.height = IMG_H
            ws.add_image(xl_img, f"B{anchor_row}")

            # Set row heights in the image area so the layout stays tidy
            for r in range(anchor_row, anchor_row + ROWS_PER_IMG):
                ws.row_dimensions[r].height = 15

            current_row += ROWS_PER_IMG + 6  # gap between charts

        except Exception:
            # Never let a bad chart image crash the whole export
            current_row += 4

    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 90

    # Place Charts sheet right after the Report Summary (position 1)
    wb.move_sheet(ws, offset=-(len(wb.sheetnames) - 2))


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------

def export_to_excel(
    results: Dict[str, Any],
    output_path: Path,
    metadata: Optional[Dict[str, Any]] = None,
    charts: Optional[List[Any]] = None,
) -> Path:
    """
    Write analysis results to a formatted multi-sheet .xlsx workbook.

    Sheets produced:
      1. Report Summary  — executive summary: question, date, summary, key finding
      2. Charts          — embedded chart images (if charts provided)
      3. Overall Summary — overall descriptive stats
      4. By Major        — per-major stats (one or two files)
      5. Group Comparison / Rankings
      6. SLO Distribution (percentages and counts)
      7. Statistical Tests
    """
    import pandas as pd

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:

        def _write(sheet_name: str, data: Any) -> None:
            """Coerce data to a DataFrame and write it, then apply formatting."""
            if isinstance(data, list) and data:
                df = pd.DataFrame(data)
            elif isinstance(data, dict) and data:
                df = pd.DataFrame([data])
            else:
                return
            name = sheet_name[:31]
            df.to_excel(writer, sheet_name=name, index=False)

        # ── Data sheets ──────────────────────────────────────────────────────

        if results.get("top_students"):
            _write("Top Students", results["top_students"])
        if results.get("bottom_students"):
            _write("Bottom Students", results["bottom_students"])
        if results.get("improvers"):
            _write("Top Improvers", results["improvers"])
        if results.get("declines"):
            _write("Biggest Declines", results["declines"])
        if results.get("grade_bands"):
            bands = results["grade_bands"]
            counts = bands.get("counts", {})
            pct    = bands.get("percentages", {})
            band_rows = [
                {"Grade Band": k, "Count": v, "%": round(pct.get(k, 0), 1)}
                for k, v in counts.items()
            ]
            if band_rows:
                _write("Grade Bands", band_rows)

        if "overall" in results:
            _write("Overall Summary", results["overall"])

        if "by_major" in results:
            _write("By Major", results["by_major"])

        if "by_major_a" in results:
            _write("By Major (Dataset 1)", results["by_major_a"])

        if "by_major_b" in results:
            _write("By Major (Dataset 2)", results["by_major_b"])

        if "stats_a" in results and "stats_b" in results:
            ttest  = results.get("ttest", {})
            cmp    = ttest.get("comparison", "")
            parts  = cmp.split(" vs ")
            name_a = parts[0].strip() if len(parts) == 2 else "Group A"
            name_b = parts[1].strip() if len(parts) == 2 else "Group B"
            _write("Major Comparison", [
                {"Major": name_a, **results["stats_a"]},
                {"Major": name_b, **results["stats_b"]},
            ])

        if "overall_stats" in results:
            rows = [{"Group": k, **v} for k, v in results["overall_stats"].items()]
            _write("Group Comparison", rows)

        if "rankings" in results:
            _write("Rankings", results["rankings"])

        for key, label in [
            ("slo_distribution", "SLO Distribution"),
            ("slo_a",            "SLO Dataset 1"),
            ("slo_b",            "SLO Dataset 2"),
        ]:
            if key in results:
                slo = results[key]
                if slo.get("percentages"):
                    _write(f"{label} %"[:31], slo["percentages"])
                if isinstance(slo.get("counts"), list):
                    _write(f"{label} Counts"[:31], slo["counts"])

        tests: list = []
        for key in ("ttest_overall", "ttest", "anova", "anova_a", "anova_b"):
            if key in results:
                tests.append(results[key])
        if "per_major_tests" in results:
            tests.extend(results["per_major_tests"])
        if tests:
            _write("Statistical Tests", tests)

        # ── Apply formatting to all data sheets ───────────────────────────────
        for sheet_name in writer.book.sheetnames:
            _format_data_sheet(writer.book[sheet_name])

        # ── Charts sheet (after data, will be repositioned) ───────────────────
        _write_charts_sheet(writer.book, charts or [])

        # ── Report Summary sheet (always inserted at position 0) ─────────────
        _write_report_summary_sheet(writer.book, metadata or {})

    return output_path


# ---------------------------------------------------------------------------
# PDF export scaffold
# ---------------------------------------------------------------------------

def export_to_pdf(summary_text: str, output_path: Path) -> Path:
    """
    Minimal PDF export.  Outputs a clean report with the NL summary.
    Full chart/table embedding will be added in Phase 4.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        doc = SimpleDocTemplate(str(output_path), pagesize=letter,
                                leftMargin=inch, rightMargin=inch,
                                topMargin=inch, bottomMargin=inch)
        styles = getSampleStyleSheet()
        story = [
            Paragraph("Faculty Analytics Report", styles["Title"]),
            Spacer(1, 0.2 * inch),
            Paragraph(summary_text.replace("\n", "<br/>"), styles["Normal"]),
        ]
        doc.build(story)

    except ImportError:
        output_path.write_text(
            "PDF export requires reportlab.\n\n" + summary_text,
            encoding="utf-8",
        )

    return output_path
