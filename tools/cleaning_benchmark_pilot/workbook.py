"""Human-review XLSX creation and safe, schema-preserving CSV write-back."""

from __future__ import annotations

import csv
import posixpath
import re
import zipfile
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any
from xml.etree import ElementTree as ET

import xlsxwriter

from .core import REVIEW_CONCLUSIONS, _read_csv


REVIEW_SHEET = "人工复核"
PATH_SHEET = "路径详情"
REGION_REVIEW_SHEET = "区域复核"
REGION_DETAILS_SHEET = "技术详情"
REVIEW_FIELDS = (
    "review_id", "item_type", "work_id", "preview_link", "human_conclusion",
    "corrected_variant", "corrected_path", "reviewer_note",
)
PATH_FIELDS = (
    "review_id", "relative_page_path", "jp_source_path", "textless_source_path",
    "zh_source_path", "review_bundle_path",
)
CORRECTED_VARIANTS = ("jp", "textless", "zh")
CSV_HUMAN_FIELDS = ("human_conclusion", "corrected_jp_path", "corrected_textless_path", "corrected_zh_path", "reviewer_note")
REGION_REVIEW_FIELDS = (
    "region_id", "work_id", "page_triplet_id", "preview_link", "page_role", "eligibility",
    "complexity_class", "mask_status", "protected_structure_status", "rejection_reason", "reviewer_note",
)
REGION_TECHNICAL_FIELDS = (
    "region_id", "source_paths", "bbox", "source_hashes", "alignment_transform",
    "registration_quality", "candidate_mask_path", "preview_path", "selection_seed", "annotation_version",
)
PAGE_ROLES = ("content", "cover", "title_page", "end_page", "credits", "scanlation_note", "advertisement", "blank", "unknown")
REGION_ELIGIBILITIES = ("gold", "silver", "reject", "pending")
COMPLEXITY_CLASSES = ("E1", "E2", "E3", "E4", "uncertain")
MASK_STATUSES = ("confirmed", "needs_edit", "invalid", "uncertain")
PROTECTED_STRUCTURE_STATUSES = ("clear", "confirmed", "needs_edit", "invalid", "uncertain")
REJECTION_REASONS = ("non_content_page", "wrong_region", "pairing_mismatch", "registration_failure", "different_base_image", "textless_residual", "textless_overpaint", "structure_changed", "mask_invalid", "not_text", "duplicate_region", "unsupported_e4", "other")
REGION_HUMAN_FIELDS = ("page_role", "eligibility", "complexity_class", "mask_status", "protected_structure_status", "rejection_reason", "reviewer_note")
REGION_ANNOTATION_VERSION = "cleaning-benchmark-pilot-v0.1"
_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships", "pkg": "http://schemas.openxmlformats.org/package/2006/relationships"}


def _relative_preview_target(workbook_path: Path, review_root: Path, bundle_path: str) -> str:
    target = review_root / bundle_path
    return Path(posixpath.relpath(target.as_posix(), workbook_path.parent.as_posix())).as_posix()


def create_manual_review_workbook(csv_path: Path, workbook_path: Path, review_root: Path) -> None:
    """Create a presentation layer; the CSV remains the sole machine fact source."""
    rows = _read_csv(csv_path)
    if not rows:
        raise RuntimeError("manual_review_resolution_csv_is_empty")
    workbook_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(workbook_path, {
        "strings_to_numbers": False,
        "strings_to_formulas": False,
        "strings_to_urls": False,
    })
    header = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1, "valign": "vcenter"})
    text = workbook.add_format({"text_wrap": True, "valign": "top", "num_format": "@"})
    link = workbook.add_format({"font_color": "#0563C1", "underline": 1, "valign": "top", "num_format": "@"})
    pending = workbook.add_format({"bg_color": "#FCE4D6", "num_format": "@"})
    green = workbook.add_format({"bg_color": "#E2F0D9", "num_format": "@"})
    red = workbook.add_format({"bg_color": "#F4CCCC", "num_format": "@"})
    yellow = workbook.add_format({"bg_color": "#FFF2CC", "num_format": "@"})

    review = workbook.add_worksheet(REVIEW_SHEET)
    review.freeze_panes(1, 0)
    review.set_row(0, 24)
    review.set_column(0, 0, 14, text)
    review.set_column(1, 1, 28, text)
    review.set_column(2, 2, 13, text)
    review.set_column(3, 3, 15, link)
    review.set_column(4, 5, 22, text)
    review.set_column(6, 6, 60, text)
    review.set_column(7, 7, 42, text)
    for column, field in enumerate(REVIEW_FIELDS):
        review.write(0, column, field, header)
    for row_index, source in enumerate(rows, start=1):
        review.set_row(row_index, 30)
        values = (
            source["review_id"], source["item_type"], source["work_id"],
            "打开预览", source["human_conclusion"], "", "", source["reviewer_note"],
        )
        for column, value in enumerate(values):
            if column == 3:
                review.write_url(row_index, column, "external:" + _relative_preview_target(workbook_path, review_root, source["review_bundle_path"]), link, value)
            else:
                review.write_string(row_index, column, value, text)
    last_row = len(rows)
    review.autofilter(0, 0, last_row, len(REVIEW_FIELDS) - 1)
    review.data_validation(1, 4, last_row, 4, {"validate": "list", "source": list(REVIEW_CONCLUSIONS)})
    review.data_validation(1, 5, last_row, 5, {"validate": "list", "source": list(CORRECTED_VARIANTS)})
    review.conditional_format(1, 4, last_row, 4, {"type": "formula", "criteria": "=E2=\"\"", "format": pending})
    review.conditional_format(1, 4, last_row, 4, {"type": "formula", "criteria": "=E2=\"confirmed_match\"", "format": green})
    review.conditional_format(1, 4, last_row, 4, {"type": "formula", "criteria": "=E2=\"reject_pair\"", "format": red})
    review.conditional_format(1, 4, last_row, 4, {"type": "formula", "criteria": "=E2=\"defer\"", "format": yellow})
    review.conditional_format(1, 5, last_row, 6, {"type": "formula", "criteria": "=AND($E2=\"corrected_match\",OR($F2=\"\",$G2=\"\"))", "format": pending})

    paths = workbook.add_worksheet(PATH_SHEET)
    paths.protect()
    paths.freeze_panes(1, 0)
    paths.set_row(0, 24)
    paths.set_column(0, 0, 14, text)
    paths.set_column(1, 5, 60, text)
    for column, field in enumerate(PATH_FIELDS):
        paths.write(0, column, field, header)
    for row_index, source in enumerate(rows, start=1):
        paths.set_row(row_index, 30)
        values = (
            source["review_id"], source["relative_path"], source["jp_source_path"],
            source["textless_source_path"], source["zh_source_path"], source["review_bundle_path"],
        )
        for column, value in enumerate(values):
            paths.write_string(row_index, column, value, text)
    workbook.close()


def _column_number(reference: str) -> int:
    result = 0
    for character in reference:
        if character.isalpha():
            result = result * 26 + ord(character.upper()) - ord("A") + 1
    return result - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(item.itertext()) for item in root.findall("main:si", _NS)]


def _review_sheet_xml_path(archive: zipfile.ZipFile) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relation_id = next((sheet.attrib.get("{" + _NS["rel"] + "}id") for sheet in workbook.findall("main:sheets/main:sheet", _NS) if sheet.attrib.get("name") == REVIEW_SHEET), None)
    if not relation_id:
        raise RuntimeError("workbook_missing_人工复核_sheet")
    relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    target = next((relation.attrib["Target"] for relation in relations.findall("pkg:Relationship", _NS) if relation.attrib.get("Id") == relation_id), None)
    if not target:
        raise RuntimeError("workbook_missing_人工复核_relationship")
    return "xl/" + target.lstrip("/")


def _cell_value(cell: ET.Element, shared: list[str]) -> tuple[str, str]:
    cell_type = cell.attrib.get("t", "n")
    if cell_type == "inlineStr":
        return "".join(cell.itertext()), cell_type
    value = cell.findtext("main:v", default="", namespaces=_NS)
    if cell_type == "s":
        return (shared[int(value)] if value else ""), cell_type
    return value, cell_type


def read_manual_review_workbook(workbook_path: Path) -> list[dict[str, tuple[str, str]]]:
    """Read only user-editable values as raw strings; never coerce Excel types."""
    with zipfile.ZipFile(workbook_path) as archive:
        shared = _shared_strings(archive)
        sheet = ET.fromstring(archive.read(_review_sheet_xml_path(archive)))
    rows: list[dict[int, tuple[str, str]]] = []
    for row in sheet.findall("main:sheetData/main:row", _NS):
        values: dict[int, tuple[str, str]] = {}
        for cell in row.findall("main:c", _NS):
            values[_column_number(cell.attrib["r"])] = _cell_value(cell, shared)
        rows.append(values)
    if not rows:
        raise RuntimeError("workbook_人工复核_sheet_is_empty")
    headers = {column: value[0] for column, value in rows[0].items()}
    expected = {field: index for index, field in enumerate(REVIEW_FIELDS)}
    if headers != {index: field for field, index in expected.items()}:
        raise RuntimeError("workbook_人工复核_schema_mismatch")
    result: list[dict[str, tuple[str, str]]] = []
    for values in rows[1:]:
        if not values:
            continue
        result.append({field: values.get(index, ("", "inlineStr")) for field, index in expected.items()})
    return result


def _require_text(value: tuple[str, str], field: str, review_id: str) -> str:
    raw, cell_type = value
    if cell_type not in {"s", "inlineStr", "str"}:
        raise RuntimeError(f"workbook_{field}_must_be_text:{review_id}")
    return raw


def _validate_posix_input_path(path: str, review_id: str, input_root: Path) -> None:
    if not path or "\\" in path or path.startswith("/") or path.startswith("//") or re.match(r"^[A-Za-z]:", path) or PureWindowsPath(path).drive:
        raise RuntimeError(f"invalid_corrected_path:{review_id}")
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise RuntimeError(f"invalid_corrected_path:{review_id}")
    native_candidate = input_root.joinpath(*candidate.parts)
    if not native_candidate.is_file() or not native_candidate.resolve().is_relative_to(input_root.resolve()):
        raise RuntimeError(f"invalid_corrected_path:{review_id}")


def _validate_correction(review: dict[str, tuple[str, str]], review_id: str, input_root: Path) -> tuple[str, str, str, str, int]:
    conclusion = _require_text(review["human_conclusion"], "human_conclusion", review_id)
    variant = _require_text(review["corrected_variant"], "corrected_variant", review_id)
    path = _require_text(review["corrected_path"], "corrected_path", review_id)
    note = _require_text(review["reviewer_note"], "reviewer_note", review_id)
    if conclusion not in REVIEW_CONCLUSIONS:
        raise RuntimeError(f"invalid_human_conclusion:{review_id}")
    cleared_anomaly_count = 0
    if conclusion != "corrected_match":
        # Some spreadsheet editors have written the visual placeholder 12 into
        # otherwise blank correction cells.  It is not a human correction.
        if variant == "12":
            variant = ""
            cleared_anomaly_count += 1
        if path == "12":
            path = ""
            cleared_anomaly_count += 1
        if variant or path:
            raise RuntimeError(f"only_corrected_match_may_set_correction_fields:{review_id}")
        return conclusion, "", "", note, cleared_anomaly_count
    if variant not in CORRECTED_VARIANTS:
        raise RuntimeError(f"invalid_corrected_variant:{review_id}")
    if not path:
        raise RuntimeError(f"corrected_match_requires_variant_and_path:{review_id}")
    _validate_posix_input_path(path, review_id, input_root)
    return conclusion, variant, path, note, cleared_anomaly_count


def validate_manual_review_workbook(workbook_path: Path, csv_path: Path, input_root: Path) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Validate a completed workbook and return immutable CSV rows plus summary."""
    csv_rows = _read_csv(csv_path)
    fieldnames = list(csv_rows[0]) if csv_rows else []
    if len(csv_rows) != 17 or not csv_rows or not set(CSV_HUMAN_FIELDS).issubset(fieldnames):
        raise RuntimeError("manual_review_resolution_csv_schema_mismatch")
    review_rows = read_manual_review_workbook(workbook_path)
    if len(review_rows) != 17:
        raise RuntimeError("workbook_must_contain_exactly_17_review_rows")
    by_id: dict[str, dict[str, tuple[str, str]]] = {}
    for review in review_rows:
        review_id = _require_text(review["review_id"], "review_id", "unknown")
        if not review_id or review_id in by_id:
            raise RuntimeError("workbook_review_id_missing_or_duplicate")
        by_id[review_id] = review
    csv_by_id = {row["review_id"]: row for row in csv_rows}
    if set(by_id) != set(csv_by_id):
        raise RuntimeError("workbook_review_ids_do_not_match_csv")
    if by_id["review-002"]["human_conclusion"][0] != "confirmed_extra_page":
        raise RuntimeError("review-002_must_be_confirmed_extra_page")
    conclusion_counts: dict[str, int] = {conclusion: 0 for conclusion in REVIEW_CONCLUSIONS}
    anomaly_count = 0
    immutable_fields = [field for field in fieldnames if field not in CSV_HUMAN_FIELDS]
    immutable_snapshot = {review_id: tuple(row[field] for field in immutable_fields) for review_id, row in csv_by_id.items()}
    for row in csv_rows:
        review = by_id[row["review_id"]]
        for field in ("item_type", "work_id"):
            if _require_text(review[field], field, row["review_id"]) != row[field]:
                raise RuntimeError(f"workbook_immutable_field_changed:{field}:{row['review_id']}")
        conclusion, variant, path, note, cleared = _validate_correction(review, row["review_id"], input_root)
        conclusion_counts[conclusion] += 1
        anomaly_count += cleared
        row["human_conclusion"] = conclusion
        row["corrected_jp_path"] = path if variant == "jp" else ""
        row["corrected_textless_path"] = path if variant == "textless" else ""
        row["corrected_zh_path"] = path if variant == "zh" else ""
        row["reviewer_note"] = note
    for row in csv_rows:
        if tuple(row[field] for field in immutable_fields) != immutable_snapshot[row["review_id"]]:
            raise RuntimeError(f"csv_immutable_field_changed:{row['review_id']}")
    return csv_rows, {**conclusion_counts, "cleared_blank_correction_anomalies": anomaly_count}


def write_back_manual_review_workbook(workbook_path: Path, csv_path: Path, input_root: Path) -> None:
    """Safely map the four human fields back without changing CSV fact columns."""
    csv_rows, _ = validate_manual_review_workbook(workbook_path, csv_path, input_root)
    fieldnames = list(csv_rows[0])
    temporary = csv_path.with_suffix(csv_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(csv_rows)
    temporary.replace(csv_path)


def _write_csv_rows(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _ensure_region_review_schema(csv_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    rows = _read_csv(csv_path)
    if len(rows) != 48:
        raise RuntimeError("region_review_csv_must_contain_exactly_48_rows")
    fieldnames = list(rows[0]) if rows else []
    if "region_id" not in fieldnames or len({row["region_id"] for row in rows}) != 48:
        raise RuntimeError("region_review_csv_region_id_schema_mismatch")
    if "page_role" not in fieldnames:
        insert_at = fieldnames.index("eligibility") if "eligibility" in fieldnames else len(fieldnames)
        fieldnames.insert(insert_at, "page_role")
        for row in rows:
            row["page_role"] = ""
        _write_csv_rows(csv_path, rows, fieldnames)
    return rows, fieldnames


def _selection_seed_by_triplet(selection_csv: Path) -> dict[str, str]:
    return {row["page_triplet_id"]: row["selection_seed"] for row in _read_csv(selection_csv)}


def create_region_review_workbook(region_csv: Path, workbook_path: Path, review_root: Path, selection_csv: Path, manual_resolution_csv: Path) -> dict[str, int]:
    """Create a two-sheet region review workbook without asserting any decision."""
    rows, _ = _ensure_region_review_schema(region_csv)
    # The completed page-level results are an overlay input only.  This function
    # deliberately never writes them or any frozen dataset-audit artifacts.
    manual_rows = _read_csv(manual_resolution_csv)
    if len(manual_rows) != 17:
        raise RuntimeError("manual_resolution_overlay_must_contain_exactly_17_rows")
    seeds = _selection_seed_by_triplet(selection_csv)
    workbook_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(workbook_path, {"strings_to_numbers": False, "strings_to_formulas": False, "strings_to_urls": False})
    header = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1, "valign": "vcenter"})
    text = workbook.add_format({"text_wrap": True, "valign": "top", "num_format": "@"})
    link = workbook.add_format({"font_color": "#0563C1", "underline": 1, "valign": "top", "num_format": "@"})
    pending = workbook.add_format({"bg_color": "#FCE4D6", "num_format": "@"})
    green = workbook.add_format({"bg_color": "#E2F0D9", "num_format": "@"})
    red = workbook.add_format({"bg_color": "#F4CCCC", "num_format": "@"})
    yellow = workbook.add_format({"bg_color": "#FFF2CC", "num_format": "@"})

    review = workbook.add_worksheet(REGION_REVIEW_SHEET)
    review.freeze_panes(1, 0)
    review.set_row(0, 24)
    for first, last, width in ((0, 0, 24), (1, 1, 13), (2, 2, 20), (3, 3, 15), (4, 5, 18), (6, 8, 24), (9, 9, 28), (10, 10, 42)):
        review.set_column(first, last, width, text if first != 3 else link)
    for column, field in enumerate(REGION_REVIEW_FIELDS):
        review.write(0, column, field, header)
    for row_index, source in enumerate(rows, start=1):
        review.set_row(row_index, 30)
        editable = {
            "page_role": source.get("page_role", ""),
            "eligibility": source.get("eligibility", "pending"),
            "complexity_class": source.get("complexity_class", ""),
            "mask_status": "" if source.get("mask_status") == "pending" else source.get("mask_status", ""),
            "protected_structure_status": "" if source.get("protected_structure_status") == "pending" else source.get("protected_structure_status", ""),
            "rejection_reason": source.get("rejection_reason", ""),
            "reviewer_note": source.get("reviewer_note", ""),
        }
        values = (source["region_id"], source["work_id"], source["page_triplet_id"], "打开预览", *(editable[field] for field in REGION_HUMAN_FIELDS))
        for column, value in enumerate(values):
            if column == 3:
                review.write_url(row_index, column, "external:" + _relative_preview_target(workbook_path, review_root, source["review_preview_path"]), link, value)
            else:
                review.write_string(row_index, column, value, text)
    last_row = len(rows)
    review.autofilter(0, 0, last_row, len(REGION_REVIEW_FIELDS) - 1)
    validations = ((4, PAGE_ROLES), (5, REGION_ELIGIBILITIES), (6, COMPLEXITY_CLASSES), (7, MASK_STATUSES), (8, PROTECTED_STRUCTURE_STATUSES), (9, REJECTION_REASONS))
    for column, choices in validations:
        review.data_validation(1, column, last_row, column, {"validate": "list", "source": list(choices)})
    # Empty fields and pending rows remain visibly incomplete; no value is inferred.
    review.conditional_format(1, 4, last_row, 4, {"type": "formula", "criteria": "=E2=\"\"", "format": pending})
    review.conditional_format(1, 5, last_row, 5, {"type": "formula", "criteria": "=F2=\"pending\"", "format": yellow})
    review.conditional_format(1, 5, last_row, 5, {"type": "formula", "criteria": "=F2=\"gold\"", "format": green})
    review.conditional_format(1, 5, last_row, 5, {"type": "formula", "criteria": "=F2=\"reject\"", "format": red})
    review.conditional_format(1, 6, last_row, 9, {"type": "formula", "criteria": "=OR($F2=\"gold\",$F2=\"silver\",$F2=\"reject\")", "format": pending})

    details = workbook.add_worksheet(REGION_DETAILS_SHEET)
    details.protect()
    details.freeze_panes(1, 0)
    details.set_row(0, 24)
    details.set_column(0, 0, 24, text)
    details.set_column(1, 1, 70, text)
    details.set_column(2, 4, 48, text)
    details.set_column(5, 5, 22, text)
    details.set_column(6, 7, 60, text)
    details.set_column(8, 9, 20, text)
    for column, field in enumerate(REGION_TECHNICAL_FIELDS):
        details.write(0, column, field, header)
    for row_index, source in enumerate(rows, start=1):
        details.set_row(row_index, 30)
        values = (
            source["region_id"],
            "\n".join((source["jp_source_path"], source["textless_source_path"], source["zh_source_path"])),
            source["bbox_xywh"],
            "\n".join((source["jp_source_sha256"], source["textless_source_sha256"], source["zh_source_sha256"])),
            source["textless_alignment_transform"], source["registration_quality"], source["candidate_mask_path"], source["review_preview_path"],
            seeds.get(source["page_triplet_id"], ""), REGION_ANNOTATION_VERSION,
        )
        for column, value in enumerate(values):
            details.write_string(row_index, column, value, text)
    workbook.close()
    return {"region_rows": len(rows), "manual_resolution_overlay_rows": len(manual_rows)}


def _region_sheet_xml_path(archive: zipfile.ZipFile) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relation_id = next((sheet.attrib.get("{" + _NS["rel"] + "}id") for sheet in workbook.findall("main:sheets/main:sheet", _NS) if sheet.attrib.get("name") == REGION_REVIEW_SHEET), None)
    if not relation_id:
        raise RuntimeError("workbook_missing_区域复核_sheet")
    relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    target = next((relation.attrib["Target"] for relation in relations.findall("pkg:Relationship", _NS) if relation.attrib.get("Id") == relation_id), None)
    if not target:
        raise RuntimeError("workbook_missing_区域复核_relationship")
    return "xl/" + target.lstrip("/")


def read_region_review_workbook(workbook_path: Path) -> list[dict[str, tuple[str, str]]]:
    with zipfile.ZipFile(workbook_path) as archive:
        shared = _shared_strings(archive)
        sheet = ET.fromstring(archive.read(_region_sheet_xml_path(archive)))
    rows: list[dict[int, tuple[str, str]]] = []
    for row in sheet.findall("main:sheetData/main:row", _NS):
        values: dict[int, tuple[str, str]] = {}
        for cell in row.findall("main:c", _NS):
            values[_column_number(cell.attrib["r"])] = _cell_value(cell, shared)
        rows.append(values)
    if not rows:
        raise RuntimeError("workbook_区域复核_sheet_is_empty")
    headers = {column: value[0] for column, value in rows[0].items()}
    expected = {field: index for index, field in enumerate(REGION_REVIEW_FIELDS)}
    if headers != {index: field for field, index in expected.items()}:
        raise RuntimeError("workbook_区域复核_schema_mismatch")
    return [{field: values.get(index, ("", "inlineStr")) for field, index in expected.items()} for values in rows[1:] if values]


def _region_text(review: dict[str, tuple[str, str]], field: str, region_id: str) -> str:
    return _require_text(review[field], field, region_id)


def _validate_region_combination(review: dict[str, tuple[str, str]], region_id: str) -> dict[str, str]:
    values = {field: _region_text(review, field, region_id) for field in REGION_HUMAN_FIELDS}
    page_role, eligibility = values["page_role"], values["eligibility"]
    enum_values = {
        "page_role": PAGE_ROLES, "eligibility": REGION_ELIGIBILITIES, "complexity_class": COMPLEXITY_CLASSES,
        "mask_status": MASK_STATUSES, "protected_structure_status": PROTECTED_STRUCTURE_STATUSES,
        "rejection_reason": REJECTION_REASONS,
    }
    for field, allowed in enum_values.items():
        if values[field] and values[field] not in allowed:
            raise RuntimeError(f"invalid_{field}:{region_id}")
    if page_role and page_role != "content":
        if eligibility != "reject" or values["rejection_reason"] != "non_content_page":
            raise RuntimeError(f"non_content_page_must_be_rejected:{region_id}")
    if eligibility in {"gold", "silver"} and page_role != "content":
        raise RuntimeError(f"eligible_region_must_be_content:{region_id}")
    if eligibility == "gold":
        if values["mask_status"] != "confirmed" or values["protected_structure_status"] not in {"clear", "confirmed"}:
            raise RuntimeError(f"gold_region_combination_invalid:{region_id}")
    if eligibility == "reject" and not values["rejection_reason"]:
        raise RuntimeError(f"reject_requires_rejection_reason:{region_id}")
    return values


def validate_region_review_workbook(workbook_path: Path, region_csv: Path, manual_resolution_csv: Path) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Validate all editable region fields while keeping machine fields immutable."""
    rows, fieldnames = _ensure_region_review_schema(region_csv)
    manual_rows = _read_csv(manual_resolution_csv)
    if len(manual_rows) != 17:
        raise RuntimeError("manual_resolution_overlay_must_contain_exactly_17_rows")
    workbook_rows = read_region_review_workbook(workbook_path)
    if len(workbook_rows) != 48:
        raise RuntimeError("workbook_must_contain_exactly_48_region_rows")
    by_id: dict[str, dict[str, tuple[str, str]]] = {}
    for review in workbook_rows:
        region_id = _region_text(review, "region_id", "unknown")
        if not region_id or region_id in by_id:
            raise RuntimeError("workbook_region_id_missing_or_duplicate")
        by_id[region_id] = review
    csv_by_id = {row["region_id"]: row for row in rows}
    if set(by_id) != set(csv_by_id):
        raise RuntimeError("workbook_region_ids_do_not_match_csv")
    immutable_fields = [field for field in fieldnames if field not in REGION_HUMAN_FIELDS]
    immutable_snapshot = {region_id: tuple(row[field] for field in immutable_fields) for region_id, row in csv_by_id.items()}
    counts: dict[str, int] = {value: 0 for value in REGION_ELIGIBILITIES}
    for row in rows:
        review = by_id[row["region_id"]]
        for field in ("work_id", "page_triplet_id"):
            if _region_text(review, field, row["region_id"]) != row[field]:
                raise RuntimeError(f"workbook_immutable_field_changed:{field}:{row['region_id']}")
        values = _validate_region_combination(review, row["region_id"])
        for field in REGION_HUMAN_FIELDS:
            row[field] = values[field]
        if values["eligibility"]:
            counts[values["eligibility"]] += 1
    for row in rows:
        if tuple(row[field] for field in immutable_fields) != immutable_snapshot[row["region_id"]]:
            raise RuntimeError(f"csv_immutable_field_changed:{row['region_id']}")
    return rows, {**counts, "manual_resolution_overlay_rows": len(manual_rows)}


def write_back_region_review_workbook(workbook_path: Path, region_csv: Path, manual_resolution_csv: Path) -> None:
    rows, _ = validate_region_review_workbook(workbook_path, region_csv, manual_resolution_csv)
    _write_csv_rows(region_csv, rows, list(rows[0]))
