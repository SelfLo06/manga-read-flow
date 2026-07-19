from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
import xlsxwriter
from PIL import Image

from tools.experiments.cleaning_150.cleaning_benchmark_pilot.core import (
    EXPLORATION_WORKS,
    _components,
    extract_candidate_regions,
    hash_tree,
    select_pages,
)
from tools.experiments.cleaning_150.cleaning_benchmark_pilot.workbook import (
    PATH_FIELDS,
    REVIEW_FIELDS,
    REVIEW_SHEET,
    REGION_REVIEW_FIELDS,
    REGION_REVIEW_SHEET,
    create_manual_review_workbook,
    create_region_review_workbook,
    read_manual_review_workbook,
    read_region_review_workbook,
    validate_manual_review_workbook,
    validate_region_review_workbook,
    write_back_manual_review_workbook,
    write_back_region_review_workbook,
)
from tools.experiments.cleaning_150.cleaning_benchmark_pilot.region_candidate_pilot import extract_container_candidates
from tools.experiments.cleaning_150.cleaning_benchmark_pilot.hard_case_supplement_v2 import _deduplicate, _select_positive, validate_v2_rows


def _triplet(work_id: str, name: str) -> dict[str, str]:
    return {
        "work_id": work_id,
        "original_path": f"{work_id}/jp/{name}.png",
        "textless_path": f"{work_id}/textless/{name}.png",
        "chinese_path": f"{work_id}/zh/{name}.png",
        "qualification": "Gold candidate",
        "textless_registration_quality": "high",
        "chinese_registration_quality": "high",
        "textless_match_score": "0.99",
        "chinese_match_score": "0.95",
        "textless_transform_matrix": "[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]",
    }


def test_selection_is_deterministic_balanced_and_excludes_unresolved() -> None:
    triplets = [_triplet(work, f"{index:02d}") for work in EXPLORATION_WORKS for index in range(6)]
    excluded = {"work-003/jp/00.png"}
    first = select_pages(triplets, excluded, seed=7, target=8)
    second = select_pages(triplets, excluded, seed=7, target=8)

    assert first == second
    assert len(first) == 8
    assert {row["work_id"] for row in first} == set(EXPLORATION_WORKS)
    assert all(row["original_path"] not in excluded for row in first)


def test_registered_difference_extracts_candidate_and_filters_tiny_components() -> None:
    textless = np.full((160, 180, 3), 255, dtype=np.uint8)
    jp = textless.copy()
    jp[30:66, 40:108] = 0
    jp[3:5, 3:5] = 0

    mask, protected, candidates = extract_candidate_regions(
        jp, textless, "[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]", min_area=96
    )

    assert mask[45, 70] == 255
    assert protected.shape == mask.shape
    assert len(candidates) == 1
    assert candidates[0]["area"] >= 96


def test_components_reject_tiny_and_page_sized_regions() -> None:
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[1:4, 1:4] = 255
    mask[20:50, 20:60] = 255
    mask[60:100, 0:100] = 255

    components = _components(mask, min_area=96)

    assert len(components) == 1
    assert components[0]["x"] == 20
    assert components[0]["y"] == 20


def test_hash_tree_detects_image_input_change(tmp_path: Path) -> None:
    source = tmp_path / "data" / "page.png"
    source.parent.mkdir(parents=True)
    Image.new("L", (10, 10), 255).save(source)
    before = hash_tree(tmp_path / "data")
    Image.new("L", (10, 10), 0).save(source)
    assert hash_tree(tmp_path / "data") != before


def _write_review_csv(path: Path) -> None:
    header = "review_id,item_type,work_id,relative_path,jp_source_path,textless_source_path,zh_source_path,review_bundle_path,human_conclusion,corrected_jp_path,corrected_textless_path,corrected_zh_path,reviewer_note\n"
    rows = []
    for index in range(1, 18):
        item_type = "extra_reference_page" if index == 2 else "pairing_unresolved"
        rows.append(f"review-{index:03d},{item_type},work-003,work/page.jpg,work/page.jpg,work/textless.jpg,work/zh.jpg,unresolved/review-{index:03d}/comparison.png,,,,,\n")
    path.write_text(header + "".join(rows), encoding="utf-8")


def test_workbook_has_review_layout_and_preserves_blank_human_fields(tmp_path: Path) -> None:
    csv_path = tmp_path / "manual-review-resolution.csv"
    workbook_path = tmp_path / "manual-review-workbook.xlsx"
    _write_review_csv(csv_path)

    create_manual_review_workbook(csv_path, workbook_path, tmp_path / "artifacts")

    review_rows = read_manual_review_workbook(workbook_path)
    assert review_rows[0]["review_id"][0] == "review-001"
    assert review_rows[0]["human_conclusion"][0] == ""
    import zipfile
    with zipfile.ZipFile(workbook_path) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode()
        review_xml = archive.read("xl/worksheets/sheet1.xml").decode()
        details_xml = archive.read("xl/worksheets/sheet2.xml").decode()
        shared_strings = archive.read("xl/sharedStrings.xml").decode()
    assert REVIEW_SHEET in workbook_xml and "路径详情" in workbook_xml
    assert "autoFilter" in review_xml and "dataValidations" in review_xml and "conditionalFormatting" in review_xml
    assert "frozen" in review_xml and "sheetProtection" in details_xml


def test_writeback_maps_only_human_fields_and_requires_text_paths(tmp_path: Path) -> None:
    csv_path = tmp_path / "manual-review-resolution.csv"
    input_root = tmp_path / "data"
    (input_root / "work").mkdir(parents=True)
    Image.new("L", (10, 10), 255).save(input_root / "work" / "textless.jpg")
    _write_review_csv(csv_path)
    workbook_path = tmp_path / "filled.xlsx"
    workbook = xlsxwriter.Workbook(workbook_path, {"strings_to_numbers": False, "strings_to_formulas": False})
    sheet = workbook.add_worksheet(REVIEW_SHEET)
    for index, field in enumerate(REVIEW_FIELDS):
        sheet.write_string(0, index, field)
    for row_index in range(1, 18):
        review_id = f"review-{row_index:03d}"
        conclusion = "confirmed_extra_page" if row_index == 2 else "confirmed_match"
        variant, path, note = "", "", ""
        if row_index == 4:
            conclusion, variant, path, note = "corrected_match", "textless", "work/textless.jpg", "checked"
        if row_index == 1:
            variant, path = "12", "12"
        values = (review_id, "extra_reference_page" if row_index == 2 else "pairing_unresolved", "work-003", "打开预览", conclusion, variant, path, note)
        for index, value in enumerate(values):
            sheet.write_string(row_index, index, value)
    workbook.close()

    _, summary = validate_manual_review_workbook(workbook_path, csv_path, input_root)
    write_back_manual_review_workbook(workbook_path, csv_path, input_root)

    import csv
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    row = rows[3]
    assert summary["cleared_blank_correction_anomalies"] == 2
    assert rows[0]["corrected_jp_path"] == rows[0]["corrected_textless_path"] == rows[0]["corrected_zh_path"] == ""
    assert row["relative_path"] == "work/page.jpg"
    assert row["human_conclusion"] == "corrected_match"
    assert row["corrected_jp_path"] == ""
    assert row["corrected_textless_path"] == "work/textless.jpg"
    assert row["corrected_zh_path"] == ""
    assert row["reviewer_note"] == "checked"


def _write_region_csv(path: Path) -> None:
    import csv
    fields = [
        "region_id", "work_id", "page_triplet_id", "jp_source_path", "textless_source_path", "zh_source_path",
        "jp_source_sha256", "textless_source_sha256", "zh_source_sha256", "bbox_xywh", "textless_alignment_transform",
        "registration_quality", "candidate_mask_path", "candidate_mask_sha256", "review_preview_path", "candidate_basis",
        "eligibility", "complexity_class", "mask_status", "protected_structure_status", "rejection_reason", "reviewer_note",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index in range(1, 49):
            writer.writerow({
                "region_id": f"region-{index:03d}", "work_id": "work-003", "page_triplet_id": "triplet-1",
                "jp_source_path": "work/jp.png", "textless_source_path": "work/textless.png", "zh_source_path": "work/zh.png",
                "jp_source_sha256": "jp", "textless_source_sha256": "textless", "zh_source_sha256": "zh",
                "bbox_xywh": "[1,2,3,4]", "textless_alignment_transform": "[[1,0,0],[0,1,0]]",
                "registration_quality": "high", "candidate_mask_path": "masks/mask.png", "candidate_mask_sha256": "mask",
                "review_preview_path": "regions/preview.png", "candidate_basis": "candidate", "eligibility": "pending",
                "complexity_class": "", "mask_status": "pending", "protected_structure_status": "pending", "rejection_reason": "", "reviewer_note": "",
            })


def test_region_workbook_hides_technical_fields_and_adds_page_role_schema(tmp_path: Path) -> None:
    region_csv = tmp_path / "region-review.csv"
    manual_csv = tmp_path / "manual-review-resolution.csv"
    selection_csv = tmp_path / "page-selection.csv"
    workbook_path = tmp_path / "region-review-workbook.xlsx"
    _write_region_csv(region_csv)
    _write_review_csv(manual_csv)
    selection_csv.write_text("page_triplet_id,selection_seed\ntriplet-1,7\n", encoding="utf-8")

    summary = create_region_review_workbook(region_csv, workbook_path, tmp_path / "artifacts", selection_csv, manual_csv)

    assert summary == {"region_rows": 48, "manual_resolution_overlay_rows": 17}
    assert len(read_region_review_workbook(workbook_path)) == 48
    import csv, zipfile
    with region_csv.open(encoding="utf-8", newline="") as handle:
        assert "page_role" in next(csv.DictReader(handle))
    with zipfile.ZipFile(workbook_path) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode()
        review_xml = archive.read("xl/worksheets/sheet1.xml").decode()
        details_xml = archive.read("xl/worksheets/sheet2.xml").decode()
        shared_strings = archive.read("xl/sharedStrings.xml").decode()
    assert REGION_REVIEW_SHEET in workbook_xml and "技术详情" in workbook_xml
    assert "bbox_xywh" not in review_xml and "dataValidations" in review_xml and "autoFilter" in review_xml
    assert "bbox" in shared_strings and "sheetProtection" in details_xml


def test_region_writeback_validates_combinations_and_preserves_machine_columns(tmp_path: Path) -> None:
    region_csv = tmp_path / "region-review.csv"
    manual_csv = tmp_path / "manual-review-resolution.csv"
    workbook_path = tmp_path / "filled-region-review.xlsx"
    _write_region_csv(region_csv)
    _write_review_csv(manual_csv)
    import csv
    with region_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0])
    fieldnames.insert(fieldnames.index("eligibility"), "page_role")
    for row in rows:
        row["page_role"] = ""
    with region_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    workbook = xlsxwriter.Workbook(workbook_path, {"strings_to_numbers": False, "strings_to_formulas": False})
    sheet = workbook.add_worksheet(REGION_REVIEW_SHEET)
    for index, field in enumerate(REGION_REVIEW_FIELDS):
        sheet.write_string(0, index, field)
    for row_index in range(1, 49):
        page_role, eligibility, complexity, mask, protected, rejection, note = "", "pending", "", "", "", "", ""
        if row_index == 1:
            page_role, eligibility, complexity, mask, protected = "content", "gold", "E1", "confirmed", "clear"
        elif row_index == 2:
            page_role, eligibility, complexity, mask, protected = "content", "silver", "E2", "needs_edit", "confirmed"
        elif row_index == 3:
            page_role, eligibility, complexity, rejection = "cover", "reject", "uncertain", "non_content_page"
        values = (f"region-{row_index:03d}", "work-003", "triplet-1", "打开预览", page_role, eligibility, complexity, mask, protected, rejection, note)
        for index, value in enumerate(values):
            sheet.write_string(row_index, index, value)
    workbook.close()

    validated, summary = validate_region_review_workbook(workbook_path, region_csv, manual_csv)
    write_back_region_review_workbook(workbook_path, region_csv, manual_csv)

    assert summary["gold"] == summary["silver"] == summary["reject"] == 1
    assert summary["pending"] == 45
    assert validated[0]["page_role"] == "content"
    with region_csv.open(encoding="utf-8", newline="") as handle:
        persisted = list(csv.DictReader(handle))
    assert persisted[0]["candidate_mask_sha256"] == "mask"
    assert persisted[2]["rejection_reason"] == "non_content_page"


def test_container_candidates_merge_vertical_columns_punctuation_small_text_outline_and_isolate_bubbles() -> None:
    textless = np.full((180, 240, 3), 90, dtype=np.uint8)
    textless[20:140, 20:105] = 255
    textless[20:140, 135:220] = 255
    jp = textless.copy()
    # Two vertical columns plus punctuation/small text in the first container.
    jp[40:100, 40:47] = 0; jp[38:105, 62:69] = 0; jp[108:113, 48:53] = 0; jp[104:112, 74:79] = 0
    cv2.rectangle(jp, (78, 62), (88, 74), (0, 0, 0), 1)  # outlined glyph fragment
    # A separate bubble must never be merged into the first one.
    jp[50:105, 165:173] = 0; jp[46:110, 188:196] = 0
    _, _, candidates, uncertain = extract_container_candidates(jp, textless, "[[1,0,0],[0,1,0]]")

    assert len(candidates) == 2
    assert not uncertain
    boxes = [candidate["container"] for candidate in candidates]
    assert any(x <= 40 and x + width >= 79 for x, _, width, _ in boxes)
    assert all(not (x < 105 and x + width > 135) for x, _, width, _ in boxes)


def test_container_candidates_marks_uncontained_or_edge_difference_uncertain() -> None:
    textless = np.full((100, 140, 3), 80, dtype=np.uint8)
    textless[20:80, 25:110] = 255
    jp = textless.copy()
    jp[1:12, 1:7] = 0  # no text container: crop would risk a page edge cut

    _, _, candidates, uncertain = extract_container_candidates(jp, textless, "[[1,0,0],[0,1,0]]")

    assert not candidates
    assert uncertain and uncertain[0]["reason"] == "candidate_generation_uncertain"


def test_hard_09_adjacent_containers_are_never_merged_by_proximity() -> None:
    """Regression fixture for the reported hard-09 cross-container merge."""
    textless = np.full((160, 240, 3), 80, dtype=np.uint8)
    textless[25:130, 20:108] = 255
    textless[25:130, 122:210] = 255
    jp = textless.copy()
    # The glyphs are deliberately close enough that the former 25px global
    # dilation would join them, but the container labels must keep them apart.
    jp[55:100, 93:100] = 0
    jp[55:100, 130:137] = 0

    _, _, candidates, uncertain = extract_container_candidates(jp, textless, "[[1,0,0],[0,1,0]]")

    assert not uncertain
    assert len(candidates) == 2
    assert all(candidate["container"][2] <= 90 for candidate in candidates)


def _dedup_candidate(page: str, bbox: tuple[int, int, int, int], marker: str) -> dict[str, object]:
    return {
        "source_page_id": page, "crop_bbox": bbox, "mask": np.pad(np.full((20, 20), 255, dtype=np.uint8), ((bbox[1], 200 - bbox[1] - 20), (bbox[0], 200 - bbox[0] - 20))),
        "crop_phash": marker, "tags": ["boundary_or_tail"],
    }


def test_v2_dedup_uses_cross_set_mask_and_self_reference() -> None:
    first = _dedup_candidate("p1", (20, 20, 40, 40), "0000000000000000")
    cross_duplicate = _dedup_candidate("p1", (20, 20, 40, 40), "0000000000000000")
    self_duplicate = _dedup_candidate("p2", (70, 70, 40, 40), "000000000000000f")
    self_duplicate_copy = _dedup_candidate("p2", (70, 70, 40, 40), "000000000000000f")
    references = [{"set": "calibration-control", "candidate_id": "pilot-01", "source_page_id": "p1", "bbox": (20, 20, 40, 40), "mask": first["mask"], "crop_phash": first["crop_phash"]}]

    kept, rejected, cross_count, self_count = _deduplicate([cross_duplicate, self_duplicate, self_duplicate_copy], references)

    assert cross_count == 1
    assert self_count == 1
    assert len(kept) == 1
    assert {item["reason"] for item in rejected} == {"cross_set_duplicate:calibration-control:pilot-01", "self_duplicate"}


def test_v2_positive_quota_selection_is_deterministic_and_role_contracts_are_strict() -> None:
    pool = []
    buckets = ["boundary_or_tail"] * 2 + ["transparent_or_textured"] * 3 + ["irregular_or_open_container"] * 2 + ["small_or_fragmented_complete_instance"]
    for index, bucket in enumerate(buckets):
        pool.append({"source_page_id": f"p{index}", "crop_bbox": (index, index, 20, 20), "crop_phash": f"{index:016x}", "tags": [bucket]})
    assert [bucket for bucket, _ in _select_positive(pool)] == buckets

    valid = [{"candidate_id": "v2-01", "candidate_role": "negative_abstention", "expected_decision": "SKIP", "abstention_reason": "not_text", "uncertainty_reason": "", "selection_reason": "fixture", "source_page_id": "p1", "crop_bbox_xywh": "[1,2,3,4]", "candidate_mask_sha256": "hash", "candidate_set_version": "supplement-v2"}]
    validate_v2_rows(valid)
    valid[0]["expected_decision"] = "REVIEW_REQUIRED"
    with pytest.raises(RuntimeError, match="negative_contract"):
        validate_v2_rows(valid)
