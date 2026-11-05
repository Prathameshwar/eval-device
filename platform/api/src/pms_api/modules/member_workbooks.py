"""Small, bounded XLSX contract. Imported cells are never evaluated."""

import re
from io import BytesIO
from zipfile import ZipFile

from defusedxml.ElementTree import fromstring
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

from pms_api.core.common import AppError, require

MAX_BYTES = 512 * 1024
MAX_ROWS = 200
HEADERS = ("Full name", "Email", "Password (optional)")
LEGACY_HEADERS = HEADERS[:2]
MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def workbook_bytes(sheets):
    book = Workbook()
    book.remove(book.active)
    for title, rows in sheets.items():
        sheet = book.create_sheet(title)
        for values in rows:
            sheet.append(values)
            # Force text storage, including strings starting with =, +, - or @.
            for cell in sheet[sheet.max_row]:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="243E53")
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = min(
                80, max(22, max(len(str(c.value or "")) for c in column) + 2)
            )
    output = BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def template_bytes(role, auth_method, department_id=None):
    return workbook_bytes(
        {
            "Members": [HEADERS],
            "Instructions": [
                ["Member import", "Instructions"],
                ["Role", role],
                ["Sign-in method", auth_method],
                ["Department", str(department_id or "Whole tenant")],
                ["Step 1", "Enter one person per row on Members. Keep both column headings."],
                [
                    "Step 2",
                    (
                        "Full name and a unique email are required. A local password is optional; leave it blank to generate one."
                        if auth_method == "local"
                        else "Full name and a unique email are required. Leave Password blank for external sign-in."
                    ),
                ],
                ["Step 3", "Save as .xlsx, upload and review validation before importing."],
                [
                    "Limits",
                    "200 people, 512 KB. Passwords must be 12-1024 characters. Blank rows are ignored.",
                ],
                ["Access", "Role, sign-in and department come from your wizard selection."],
                [
                    "Invitations",
                    "Members must accept their invitation. New local account passwords are available to tenant administrators for 30 days.",
                ],
            ],
        }
    )


def parse_workbook(data: bytes) -> list[dict]:
    require(0 < len(data) <= MAX_BYTES, "import_file_size", "Choose an Excel file no larger than 512 KB")
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            names = [item.filename for item in entries]
            require(
                len(entries) <= 80
                and len(set(names)) == len(names)
                and sum(item.file_size for item in entries) <= 4 * 1024 * 1024,
                "import_workbook_limit",
                "This workbook is too complex; use a fresh template",
            )
            for entry in entries:
                name = entry.filename.lower()
                require(
                    not entry.flag_bits & 1 and ".." not in name.split("/"),
                    "import_invalid_workbook",
                    "The workbook could not be read. Save an unencrypted .xlsx file and try again",
                )
                if name.endswith((".xml", ".rels")):
                    root = fromstring(archive.read(entry))
                    if name.startswith("xl/worksheets/"):
                        # Do not trust worksheet dimensions: inspect actual row/cell addresses.
                        for node in root.iter():
                            tag = node.tag.rsplit("}", 1)[-1]
                            if tag == "row":
                                require(
                                    int(node.get("r", "0")) <= MAX_ROWS + 1,
                                    "import_row_limit",
                                    "Use at most 200 rows per workbook",
                                )
                            if tag == "c":
                                address = node.get("r", "")
                                position = re.fullmatch(r"([A-F])([1-9][0-9]{0,2})", address)
                                require(
                                    position is not None and int(position[2]) <= MAX_ROWS + 1,
                                    "import_columns",
                                    "Use the supplied workbook columns and at most 200 rows",
                                )

        book = load_workbook(BytesIO(data), read_only=True, data_only=False, keep_links=False)
        cached_book = None
        try:
            require("Members" in book.sheetnames, "import_sheet", "The workbook needs a Members sheet")
            sheet = book["Members"]
            sheet.reset_dimensions()
            source_rows = list(sheet.iter_rows())
            value_rows = source_rows
            if any(cell.data_type == "f" for row in source_rows for cell in row):
                # Read saved formula results only; never evaluate formulas or fetch links.
                cached_book = load_workbook(BytesIO(data), read_only=True, data_only=True, keep_links=False)
                cached_sheet = cached_book["Members"]
                cached_sheet.reset_dimensions()
                value_rows = list(cached_sheet.iter_rows())
            first = value_rows[0] if value_rows else ()
            require(
                tuple(str(c.value or "").strip() for c in first) in {HEADERS, LEGACY_HEADERS},
                "import_headers",
                "Keep the Full name, Email, and optional Password headings exactly as in the template",
            )
            rows = []
            for number, (source_cells, cells) in enumerate(
                zip(source_rows[1:], value_rows[1:], strict=True), 2
            ):
                if all(c.value is None or str(c.value).strip() == "" for c in source_cells):
                    continue
                require(number <= MAX_ROWS + 1, "import_row_limit", "Use at most 200 rows per workbook")
                values = [str(c.value or "").strip()[:1000] for c in cells[:2]]
                password = cells[2].value if len(cells) > 2 else None
                problem = None
                missing_results = [
                    HEADERS[index]
                    for index, cell in enumerate(source_cells[:3])
                    if cell.data_type == "f"
                    and cells[index].value is None
                    and cells[index].data_type != "str"
                ]
                if not missing_results and all(c.value is None or str(c.value).strip() == "" for c in cells):
                    continue
                error_cells = [
                    HEADERS[index] for index, cell in enumerate(cells[:3]) if cell.data_type == "e"
                ]
                if len(cells) > 3:
                    problem = "Use only the Full name, Email, and optional Password columns."
                elif missing_results:
                    problem = (
                        "No saved value for "
                        + ", ".join(missing_results)
                        + ". Recalculate and save the workbook in Excel, then upload it again."
                    )
                elif error_cells:
                    problem = "Fix the Excel error in " + ", ".join(error_cells) + " and save the workbook."
                elif any(c.value is not None and not isinstance(c.value, str) for c in cells):
                    problem = "Enter the full name and email as text."
                values += ["", ""]
                rows.append(
                    {
                        "row_number": number,
                        "full_name": values[0],
                        "email": values[1],
                        "password": password if isinstance(password, str) else "",
                        "status": "invalid" if problem else "ready",
                        "message": problem,
                        "code": "invalid_cells" if problem else None,
                        "membership_id": None,
                    }
                )
            require(rows, "import_empty", "Add at least one person to the Members sheet")
            return rows
        finally:
            if cached_book is not None:
                cached_book.close()
            book.close()
    except AppError:
        raise
    except Exception as error:
        # XML/parser exceptions can contain document contents; never expose them.
        raise AppError(
            422, "import_invalid_workbook", "The file could not be read. Use a fresh .xlsx template."
        ) from error
