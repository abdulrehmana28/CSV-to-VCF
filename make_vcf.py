#!/usr/bin/env python3
"""
Offline CSV/Excel -> WhatsApp VCF converter for Seerah batches.

Reads a local student export, normalizes Pakistani WhatsApp numbers to
+92XXXXXXXXXX, and writes one vCard 3.0 file per batch. Contact names include
the batch code so they can be found in WhatsApp.

No network access is used. Nothing is uploaded anywhere.

Examples:
    python3 make_vcf.py --input students.csv --code SCRYK-8001
    python3 make_vcf.py --input students.xlsx
    python3 webapp.py
"""

import argparse
import csv
import io
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

# ==============================
# SETTINGS — EDIT THESE
# ==============================

INPUT_FILE = "students.csv"
BATCH_CODE_OVERRIDE = ""  # blank = use the Batch column
SHEET_NAME = 0                  # Excel only: sheet index or name

NAME_COL = "Full Name"
PHONE_COL = "Whatsapp Number"
BATCH_COL = "Batch"

OUTPUT_DIR = "vcf_output"
REPORT_FILE = "vcf_skipped_rows.csv"

SHOW_CODE_IN_NAME = True

# "brackets" => [SCRYK8-41] Ahmed Ali
# "dash"     => SCRYK8-41 - Ahmed Ali
# "parentheses" => Ahmed Ali (SCRYK8-41)
# "prefix"   => SCRYK8-41 Ahmed Ali
CODE_STYLE = "brackets"

# Fallbacks used when the configured column is not present.
NAME_COL_ALIASES = ("Full Name", "Student Name", "Name")
PHONE_COL_ALIASES = (
    "Whatsapp Number", "WhatsApp Number", "Mobile Number", "Phone",
    "Student Whatsapp Number", "Student WhatsApp Number",
)
BATCH_COL_ALIASES = ("Batch", "Batch Code", "Group")

CODE_STYLES = ("brackets", "dash", "parentheses", "prefix")
REPORT_HEADER = ["Row", "Name", "Phone", "Batch", "Reason"]

# ==============================
# CODE BELOW
# ==============================


class InputError(Exception):
    """A problem the user can fix (missing columns, bad file, etc.)."""

    def __init__(self, message, columns=None):
        super().__init__(message)
        self.columns = columns


def vcard_escape(text):
    """Escape special vCard characters."""
    text = str(text)
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\r\n", "\\n")
    text = text.replace("\r", "\\n")
    text = text.replace("\n", "\\n")
    return text.strip()


def clean_pakistan_number(raw):
    """Return +92XXXXXXXXXX for a valid Pakistani mobile number, else None."""
    if raw is None:
        return None

    s = str(raw).strip()
    if not s:
        return None

    # Excel sometimes stores numbers like 3001234567.0
    if s.lower().endswith(".0"):
        s = s[:-2]

    # Excel sometimes stores numbers like 3.00123E+9
    if "e" in s.lower():
        try:
            s = str(int(float(s)))
        except (ValueError, OverflowError):
            return None

    digits = re.sub(r"\D", "", s)

    # 03001234567
    if len(digits) == 11 and digits.startswith("03"):
        return "+92" + digits[1:]

    # 00923001234567
    if len(digits) == 14 and digits.startswith("00923"):
        return "+92" + digits[4:]

    # 923001234567 or +923001234567
    if len(digits) == 12 and digits.startswith("923"):
        return "+" + digits

    # 3001234567
    if len(digits) == 10 and digits.startswith("3"):
        return "+92" + digits

    return None


def safe_filename(name):
    name = re.sub(r'[\\/:*?"<>|]', "_", str(name)).strip()
    return name or "UNKNOWN_BATCH"


def format_display_name(batch_code, name, show_code=True, code_style=CODE_STYLE):
    batch_code = str(batch_code).strip() if batch_code is not None else ""
    name = str(name).strip() if name is not None else ""

    if not show_code or not batch_code:
        return name

    if code_style == "brackets":
        return f"[{batch_code}] {name}"
    if code_style == "dash":
        return f"{batch_code} - {name}"
    if code_style == "parentheses":
        return f"{name} ({batch_code})"
    return f"{batch_code} {name}"


def pick_column(columns, preferred, aliases):
    """Find preferred column, then aliases, ignoring case and extra spaces."""
    normalized = {str(c).strip().lower(): c for c in columns}

    for candidate in (preferred,) + aliases:
        match = normalized.get(str(candidate).strip().lower())
        if match is not None:
            return match

    return None


# ------------------------------
# Input parsing (CSV and XLSX)
# ------------------------------


def _unique_headers(raw_headers):
    headers = []
    seen = {}
    for index, header in enumerate(raw_headers):
        name = str(header).strip() if header is not None else ""
        if not name:
            name = f"Column {index + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 1
        headers.append(name)
    return headers


def _table_to_rows(table):
    """Turn a list of lists into (rows, headers), skipping blank rows."""
    if not table:
        raise InputError("The file is empty.")

    headers = _unique_headers(table[0])
    rows = []

    for line_number, values in enumerate(table[1:], start=2):
        if not any(value is not None and str(value).strip() for value in values):
            continue
        row = {
            header: (values[i] if i < len(values) else None)
            for i, header in enumerate(headers)
        }
        row["__source_row__"] = line_number
        rows.append(row)

    return rows, headers


def _decode_text(data):
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def read_csv_bytes(data):
    text = _decode_text(data)
    table = list(csv.reader(io.StringIO(text)))
    return _table_to_rows(table)


# Namespace helpers for reading .xlsx without third-party libraries.
_XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_XLSX_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_XLSX_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _col_index(cell_ref):
    """Convert an Excel cell reference like 'AB12' to a zero-based column index."""
    letters = re.match(r"[A-Za-z]+", cell_ref or "")
    if not letters:
        return None
    index = 0
    for char in letters.group(0).upper():
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _xlsx_text(element):
    return "".join(
        node.text or ""
        for node in element.iter(f"{{{_XLSX_NS}}}t")
    )


def _xlsx_sheet_path(archive, sheet_name):
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    sheets = workbook.findall(f"{{{_XLSX_NS}}}sheets/{{{_XLSX_NS}}}sheet")
    if not sheets:
        raise InputError("The Excel workbook has no sheets.")

    chosen = None
    if isinstance(sheet_name, int):
        if 0 <= sheet_name < len(sheets):
            chosen = sheets[sheet_name]
    else:
        wanted = str(sheet_name).strip()
        for sheet in sheets:
            if sheet.get("name") == wanted:
                chosen = sheet
                break
        if chosen is None and wanted.isdigit():
            index = int(wanted)
            if 0 <= index < len(sheets):
                chosen = sheets[index]

    if chosen is None:
        names = ", ".join(sheet.get("name", "?") for sheet in sheets)
        raise InputError(f"Sheet not found. Available sheets: {names}")

    rel_id = chosen.get(f"{{{_XLSX_REL_NS}}}id")
    target = None

    if rel_id and "xl/_rels/workbook.xml.rels" in archive.namelist():
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        for rel in rels.findall(f"{{{_XLSX_PKG_REL_NS}}}Relationship"):
            if rel.get("Id") == rel_id:
                target = rel.get("Target")
                break

    if not target:
        position = sheets.index(chosen) + 1
        target = f"worksheets/sheet{position}.xml"

    target = target.replace("\\", "/").lstrip("/")
    if not target.startswith("xl/"):
        target = "xl/" + target

    # Normalize any ../ segments in the relationship target.
    parts = []
    for part in target.split("/"):
        if part == "..":
            if parts:
                parts.pop()
        elif part not in ("", "."):
            parts.append(part)
    target = "/".join(parts)

    if target not in archive.namelist():
        fallback = sorted(
            name for name in archive.namelist()
            if name.startswith("xl/worksheets/") and name.endswith(".xml")
        )
        if not fallback:
            raise InputError("No worksheet found in the Excel file.")
        target = fallback[0]

    return target


def read_xlsx_bytes(data, sheet_name=0):
    """Read an .xlsx file using only the Python standard library."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise InputError("This is not a valid .xlsx file.")

    with archive:
        names = set(archive.namelist())
        if "xl/workbook.xml" not in names:
            raise InputError("This is not a valid .xlsx file.")

        shared = []
        if "xl/sharedStrings.xml" in names:
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in shared_root.findall(f"{{{_XLSX_NS}}}si"):
                shared.append(_xlsx_text(item))

        sheet_path = _xlsx_sheet_path(archive, sheet_name)
        sheet_root = ET.fromstring(archive.read(sheet_path))

        table = []
        for row in sheet_root.iter(f"{{{_XLSX_NS}}}row"):
            values = []
            for cell in row.findall(f"{{{_XLSX_NS}}}c"):
                index = _col_index(cell.get("r", ""))
                if index is None:
                    index = len(values)

                while len(values) <= index:
                    values.append(None)

                cell_type = cell.get("t")
                value_node = cell.find(f"{{{_XLSX_NS}}}v")
                value = value_node.text if value_node is not None else None

                if cell_type == "s" and value is not None:
                    try:
                        value = shared[int(value)]
                    except (ValueError, IndexError):
                        value = None
                elif cell_type == "inlineStr":
                    inline = cell.find(f"{{{_XLSX_NS}}}is")
                    value = _xlsx_text(inline) if inline is not None else None
                elif cell_type == "b":
                    value = "TRUE" if value == "1" else "FALSE"
                elif cell_type == "e":
                    value = value or "#ERROR"

                values[index] = value

            # Trim trailing empty cells so rows stay compact.
            while values and (values[-1] is None or str(values[-1]).strip() == ""):
                values.pop()
            table.append(values)

    return _table_to_rows(table)


def parse_input_bytes(data, filename, sheet_name=SHEET_NAME):
    suffix = Path(str(filename)).suffix.lower()
    if suffix == ".csv":
        return read_csv_bytes(data)
    if suffix in (".xlsx", ".xlsm"):
        return read_xlsx_bytes(data, sheet_name)
    raise InputError("Unsupported file type. Please upload a .csv or .xlsx file.")


# ------------------------------
# Conversion
# ------------------------------


def convert_rows(rows, columns, code_override="", show_code=True,
                 code_style=CODE_STYLE, name_col=None, phone_col=None,
                 batch_col=None):
    """Convert parsed rows into per-batch vCards and a skipped-row report."""
    if not rows:
        raise InputError("This file has no data rows to convert.")

    name_col = name_col or pick_column(columns, NAME_COL, NAME_COL_ALIASES)
    phone_col = phone_col or pick_column(columns, PHONE_COL, PHONE_COL_ALIASES)
    batch_col = batch_col or pick_column(columns, BATCH_COL, BATCH_COL_ALIASES)

    missing = []
    if not name_col:
        missing.append(NAME_COL)
    if not phone_col:
        missing.append(PHONE_COL)
    if not batch_col and not str(code_override).strip():
        missing.append(BATCH_COL)

    if missing:
        raise InputError(
            "Missing required column(s): " + ", ".join(missing) + ". "
            "Add a batch code above, or upload a file that has these columns.",
            columns=columns,
        )

    if not str(code_override).strip() and batch_col:
        has_batch_value = any(
            str(row.get(batch_col) or "").strip() for row in rows
        )
        if not has_batch_value:
            raise InputError(
                "This file's Batch column is empty. Enter a batch code above, "
                "for example SCRYK-8001, and try again."
            )

    if code_style not in CODE_STYLES:
        code_style = "brackets"

    batches = {}
    skipped = []
    total_contacts = 0

    for index, row in enumerate(rows, start=2):
        source_row = row.get("__source_row__", index)
        raw_name = row.get(name_col)
        raw_phone = row.get(phone_col)
        raw_batch = code_override or row.get(batch_col)

        name = str(raw_name).strip() if raw_name is not None else ""
        phone = clean_pakistan_number(raw_phone)
        batch_code = str(raw_batch).strip() if raw_batch is not None else ""

        if not name:
            skipped.append({
                "row": source_row, "name": raw_name, "phone": raw_phone,
                "batch": batch_code, "reason": "Missing name",
            })
            continue

        if not phone:
            skipped.append({
                "row": source_row, "name": name, "phone": raw_phone,
                "batch": batch_code, "reason": "Invalid Pakistani WhatsApp number",
            })
            continue

        if not batch_code:
            skipped.append({
                "row": source_row, "name": name, "phone": raw_phone,
                "batch": batch_code, "reason": "Missing batch code",
            })
            continue

        batch = batches.setdefault(batch_code, {
            "code": batch_code,
            "numbers": set(),
            "lines": [],
            "preview": [],
        })

        if phone in batch["numbers"]:
            skipped.append({
                "row": source_row, "name": name, "phone": phone,
                "batch": batch_code, "reason": "Duplicate number in same batch",
            })
            continue

        batch["numbers"].add(phone)
        display_name = format_display_name(batch_code, name, show_code, code_style)
        escaped_name = vcard_escape(display_name)

        batch["lines"].extend([
            "BEGIN:VCARD",
            "VERSION:3.0",
            f"N:;{escaped_name};;;",
            f"FN:{escaped_name}",
            f"TEL;TYPE=CELL:{phone}",
            f"CATEGORIES:{vcard_escape(batch_code)}",
            f"NOTE:Batch code: {vcard_escape(batch_code)}",
            "END:VCARD",
        ])
        batch["preview"].append({"name": display_name, "phone": phone})
        total_contacts += 1

    used_names = set()
    output_batches = []

    for batch in batches.values():
        if not batch["lines"]:
            continue

        base_name = safe_filename(batch["code"])
        final_name = base_name
        counter = 2
        while final_name in used_names:
            final_name = f"{base_name}_{counter}"
            counter += 1
        used_names.add(final_name)

        output_batches.append({
            "code": batch["code"],
            "contacts": len(batch["numbers"]),
            "filename": f"{final_name}.vcf",
            "vcf": "\r\n".join(batch["lines"]) + "\r\n",
            "preview": batch["preview"],
        })

    return {
        "columns": {"name": name_col, "phone": phone_col, "batch": batch_col},
        "batches": output_batches,
        "skipped": skipped,
        "total_rows": len(rows),
        "total_contacts": total_contacts,
    }


def convert_bytes(data, filename, code_override="", show_code=True,
                  code_style=CODE_STYLE, sheet_name=SHEET_NAME):
    rows, columns = parse_input_bytes(data, filename, sheet_name)
    return convert_rows(rows, columns, code_override, show_code, code_style)


def write_outputs(result, output_dir=OUTPUT_DIR, report_path=REPORT_FILE):
    """Write VCF files and the skipped-row report to disk."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    written = []
    for batch in result["batches"]:
        file_path = output / batch["filename"]
        file_path.write_bytes(batch["vcf"].encode("utf-8"))
        written.append(file_path)

    report = Path(report_path)
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(REPORT_HEADER)
        for item in result["skipped"]:
            writer.writerow([
                item["row"], item["name"], item["phone"],
                item["batch"], item["reason"],
            ])

    return written, report


# ------------------------------
# Command line
# ------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert a local student CSV/Excel file into per-batch WhatsApp VCF files."
    )
    parser.add_argument("--input", default=INPUT_FILE,
                        help=f"Input .csv/.xlsx (default: {INPUT_FILE})")
    parser.add_argument("--code", default=BATCH_CODE_OVERRIDE,
                        help="Force one batch code for every row, e.g. SCRYK8-41")
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    parser.add_argument("--report", default=REPORT_FILE)
    parser.add_argument("--sheet", default=str(SHEET_NAME),
                        help="Excel sheet name or index")
    parser.add_argument("--style", default=CODE_STYLE, choices=CODE_STYLES,
                        help="How the code appears in contact names")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        return 1

    sheet_name = args.sheet
    if sheet_name.isdigit():
        sheet_name = int(sheet_name)

    try:
        result = convert_bytes(
            input_path.read_bytes(),
            input_path.name,
            code_override=args.code.strip(),
            show_code=SHOW_CODE_IN_NAME,
            code_style=args.style,
            sheet_name=sheet_name,
        )
    except InputError as error:
        print(f"ERROR: {error}")
        if error.columns:
            print("Available columns:")
            print(list(error.columns))
        return 1

    if not result["batches"]:
        print("No valid contacts found.")

    written, report = write_outputs(result, args.output_dir, args.report)

    for batch, file_path in zip(result["batches"], written):
        print(f"Created: {file_path} | contacts: {batch['contacts']}")

    print(f"Skipped rows report saved: {report} ({len(result['skipped'])} rows)")
    print(f"Done. Total contacts written: {result['total_contacts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
