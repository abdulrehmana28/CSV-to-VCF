#!/usr/bin/env python3
"""
Offline VCF -> Google Sheets call-sheet converter.

Reads a .vcf file containing contact cards and writes a CSV with one row per
contact. The CSV adds three tracking columns used by the calling team:

    Phone Called | Is Received | Reason

Phone Called and Is Received start as "No"; Reason starts empty.

No network access is used. Nothing is uploaded anywhere.
"""

import csv
import quopri
import re
from pathlib import Path

from make_vcf import InputError, clean_pakistan_number, safe_filename

OUTPUT_HEADER = ["Name", "Phone", "Phone Called", "Is Received", "Reason"]
DEFAULT_PHONE_CALLED = "No"
DEFAULT_IS_RECEIVED = "No"


# ------------------------------
# Text helpers
# ------------------------------


def _decode_text(data):
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _unfold_lines(text):
    """Join folded vCard lines (continuations start with a space or tab)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for raw in text.split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _unescape(value):
    """Turn vCard escapes such as \\n, \\, and \\; into normal text."""
    if value is None:
        return ""

    result = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 1 < len(value):
            escaped = value[index + 1]
            result.append("\n" if escaped in ("n", "N") else escaped)
            index += 2
        else:
            result.append(char)
            index += 1
    return "".join(result).strip()


def _split_unescaped(value, separator=";"):
    """Split on a separator while preserving backslash escapes."""
    parts = []
    current = []
    escaped = False

    for char in value:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            current.append(char)
            escaped = True
        elif char == separator:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)

    parts.append("".join(current))
    return parts


def _property_parts(line):
    """Return (NAME, value, params) for a vCard property line."""
    if ":" not in line:
        return None, None, []

    left, value = line.split(":", 1)
    pieces = left.split(";")
    name = pieces[0].strip()

    # Some clients write group prefixes such as "item1.TEL".
    if "." in name:
        name = name.rsplit(".", 1)[1]

    return name.upper(), value, pieces[1:]


def _decode_property_value(value, params):
    encoding = ""
    for param in params:
        key, _, setting = param.partition("=")
        if key.strip().upper() == "ENCODING":
            encoding = setting.strip().upper()

    if encoding == "QUOTED-PRINTABLE":
        try:
            return quopri.decodestring(value.encode("utf-8")).decode("utf-8", "replace")
        except (ValueError, UnicodeDecodeError):
            return value

    return value


def _format_structured_name(value):
    """Build a display name from the vCard N property."""
    parts = [_unescape(part) for part in _split_unescaped(value)]
    parts += [""] * (5 - len(parts))
    family, given, additional, prefix, suffix = parts[:5]
    pieces = [prefix, given, additional, family, suffix]
    return " ".join(piece for piece in pieces if piece).strip()


def _normalize_phone(raw):
    """Return a usable phone number, or None when the value is too short."""
    if raw is None:
        return None

    value = str(raw).strip()
    if not value:
        return None

    if value.lower().startswith("tel:"):
        value = value[4:].strip()

    pakistani = clean_pakistan_number(value)
    if pakistani:
        return pakistani

    digits = re.sub(r"\D", "", value)
    if len(digits) < 7:
        return None

    if value.startswith("+"):
        return "+" + digits
    if digits.startswith("00"):
        return "+" + digits[2:]
    return digits


def _phone_priority(params):
    joined = ";".join(params).upper()
    if "CELL" in joined or "WHATSAPP" in joined:
        return 0
    if "VOICE" in joined or "MAIN" in joined:
        return 1
    return 2


# ------------------------------
# VCF parsing
# ------------------------------


def _card_lines(card):
    """Join quoted-printable soft line breaks inside one card."""
    lines = []
    for line in card:
        if lines and lines[-1].endswith("=") and not line.startswith((" ", "\t")):
            lines[-1] = lines[-1][:-1] + line
        else:
            lines.append(line)
    return lines


def _parse_card(card):
    name = ""
    structured_name = ""
    phones = []

    for line in _card_lines(card):
        prop_name, raw_value, params = _property_parts(line)
        if prop_name is None:
            continue

        value = _decode_property_value(raw_value, params)

        if prop_name == "FN" and not name:
            name = _unescape(value)
        elif prop_name == "N" and not structured_name:
            structured_name = _format_structured_name(value)
        elif prop_name == "TEL":
            phone = _normalize_phone(_unescape(value))
            if phone:
                phones.append((_phone_priority(params), phone))

    if not name:
        name = structured_name

    phones.sort(key=lambda item: item[0])
    phone = phones[0][1] if phones else None
    return name, phone


def parse_vcf_bytes(data):
    """Parse a VCF file into contacts. Raises InputError for unusable files."""
    text = _decode_text(data)
    lines = _unfold_lines(text)

    cards = []
    current = None

    for raw_line in lines:
        line = raw_line.lstrip("\ufeff")
        upper = line.strip().upper()

        if upper.startswith("BEGIN:VCARD"):
            current = []
        elif upper.startswith("END:VCARD"):
            if current is not None:
                cards.append(current)
            current = None
        elif current is not None and line.strip():
            current.append(line)

    # Tolerate a missing END:VCARD at the end of the file.
    if current is not None:
        cards.append(current)

    if not cards:
        raise InputError(
            "This file does not contain any contacts. Choose a .vcf file with "
            "BEGIN:VCARD and END:VCARD entries."
        )

    contacts = []
    for card in cards:
        name, phone = _parse_card(card)
        contacts.append({"name": name, "phone": phone})
    return contacts


# ------------------------------
# Call-sheet conversion
# ------------------------------


def convert_vcf_bytes(data, filename=""):
    """Convert VCF bytes into call-sheet rows and skipped-contact details."""
    contacts = parse_vcf_bytes(data)

    rows = []
    skipped = []

    for index, contact in enumerate(contacts, start=1):
        if not contact["phone"]:
            skipped.append({
                "contact": index,
                "name": contact["name"],
                "reason": "Missing phone number",
            })
            continue

        rows.append({
            "name": contact["name"],
            "phone": contact["phone"],
            "phone_called": DEFAULT_PHONE_CALLED,
            "is_received": DEFAULT_IS_RECEIVED,
            "reason": "",
        })

    if not rows:
        raise InputError(
            "No contacts with a phone number were found in this VCF file. "
            "Check that the contacts contain TEL lines."
        )

    return {
        "source": str(filename or ""),
        "rows": rows,
        "skipped": skipped,
        "total_contacts": len(contacts),
        "total_rows": len(rows),
    }


def output_filename(source_filename):
    source = str(source_filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    stem = Path(source).stem.lstrip(".")
    base = safe_filename(stem) or "contacts"
    return f"{base}_call_sheet.csv"


def write_call_sheet(result, output_dir, source_filename):
    """Write the call-sheet CSV and return its path."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    path = output / output_filename(source_filename)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(OUTPUT_HEADER)
        for row in result["rows"]:
            writer.writerow([
                row["name"],
                row["phone"],
                row["phone_called"],
                row["is_received"],
                row["reason"],
            ])

    return path
