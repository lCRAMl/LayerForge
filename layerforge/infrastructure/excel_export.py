"""Excel workbook with exactly two worksheets: Patterns and Packages."""

from __future__ import annotations

from pathlib import Path

from layerforge import APP_NAME
from layerforge.domain.export_model import ExportSnapshot

PATTERN_HEADERS = ["PatternId", "FirstPackageIndex", "PackageCount", "Width", "Height", "ValidWhile"]
PACKAGE_HEADERS = ["GlobalPackageIndex", "PatternId", "Sequence", "BaseOrientation",
                   "KxL", "KxB", "KxD", "KyL", "KyB", "KyD", "XFormula", "YFormula"]
COEFF_FORMAT = "0.0###"          # 1 -> 1.0, -0.25 -> -0.25, 0.0625 -> 0.0625
# Alternating light fill per pattern block: the "grouping by PatternId" that stays
# readable without Excel outlines (adjacent outline groups would merge anyway).
BLOCK_FILL = "F2F4F7"


def write(snapshot: ExportSnapshot, path: str | Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, PatternFill
    from openpyxl.worksheet.table import Table, TableStyleInfo

    wb = Workbook()
    wb.properties.creator = APP_NAME
    style = TableStyleInfo(name="TableStyleLight1", showRowStripes=False)

    ws = wb.active
    ws.title = "Patterns"
    ws.append(PATTERN_HEADERS)
    for row in snapshot.patterns:
        # ValidWhile: the KL/KB/D range in which the coefficients of this pattern hold.
        ws.append([row.pattern_id, row.first_index, row.count, row.width.text(), row.height.text(),
                   "; ".join(row.valid_while) or "always"])
    table = Table(displayName="Patterns", ref=f"A1:F{len(snapshot.patterns) + 1}")
    table.tableStyleInfo = style
    ws.add_table(table)
    ws.freeze_panes = "A2"
    for column, width in zip("ABCDEF", (12, 19, 15, 24, 24, 40)):
        ws.column_dimensions[column].width = width

    ws = wb.create_sheet("Packages")
    ws.append(PACKAGE_HEADERS)
    fill = PatternFill("solid", fgColor=BLOCK_FILL)
    block, previous = -1, None
    for row in snapshot.packages:
        if row.pattern_id != previous:
            block, previous = block + 1, row.pattern_id
        shaded = block % 2 == 1
        ws.append([row.global_index, row.pattern_id, row.sequence, row.orientation,
                   *(float(c) for c in row.kx.coefficients()),
                   *(float(c) for c in row.ky.coefficients()),
                   row.kx.text(), row.ky.text()])
        r = ws.max_row
        for col in range(5, 11):
            ws.cell(r, col).number_format = COEFF_FORMAT
        if shaded:
            for col in range(1, len(PACKAGE_HEADERS) + 1):
                ws.cell(r, col).fill = fill
    last = len(snapshot.packages) + 1
    table = Table(displayName="Packages", ref=f"A1:L{last}")
    table.tableStyleInfo = style
    ws.add_table(table)
    ws.freeze_panes = "A2"
    widths = (20, 11, 10, 17, 8, 8, 8, 8, 8, 8, 30, 30)
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(1, index).column_letter].width = width
    for r in range(2, last + 1):
        for col in (11, 12):
            ws.cell(r, col).alignment = Alignment(horizontal="left")
    wb.save(str(path))


def verify(path: str | Path, snapshot: ExportSnapshot) -> None:
    """Re-open the written file and compare it with the snapshot (transactional export)."""
    from openpyxl import load_workbook

    wb = load_workbook(str(path), read_only=True)
    try:
        if wb.sheetnames != ["Patterns", "Packages"]:
            raise ValueError(f"unexpected worksheets {wb.sheetnames}")
        patterns = list(wb["Patterns"].iter_rows(values_only=True))
        packages = list(wb["Packages"].iter_rows(values_only=True))
    finally:
        wb.close()
    if list(patterns[0]) != PATTERN_HEADERS or list(packages[0]) != PACKAGE_HEADERS:
        raise ValueError("unexpected header row")
    if len(patterns) - 1 != len(snapshot.patterns) or len(packages) - 1 != len(snapshot.packages):
        raise ValueError("row count does not match the export data")
    for values, row in zip(packages[1:], snapshot.packages):
        expected = [float(c) for c in row.kx.coefficients() + row.ky.coefficients()]
        if list(values[4:10]) != expected:
            raise ValueError(f"coefficients of package {row.global_index} differ")
