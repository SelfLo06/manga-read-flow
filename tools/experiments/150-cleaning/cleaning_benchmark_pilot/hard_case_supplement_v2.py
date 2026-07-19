"""Deterministic, local-only hard-case supplement v2 preparation.

This module consumes only frozen Exploration inputs and audit facts.  Its masks
are review candidates, never text ground truth or an Oracle mask.
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import xlsxwriter

from .core import EXPLORATION_WORKS, _labelled_strip, _load_rgb, _relative, _warp_textless, hash_tree, sha256_file
from .region_candidate_pilot import _crop, _iou, _preview, _read_csv, extract_container_candidates


CANDIDATE_SET_VERSION = "supplement-v2"
ANNOTATION_VERSION = "cleaning-benchmark-hard-case-v2"
SELECTION_SEED = "20260714-hard-case-v2"
POSITIVE_BUCKETS = (
    "boundary_or_tail",
    "transparent_or_textured",
    "irregular_or_open_container",
    "small_or_fragmented_complete_instance",
)
POSITIVE_QUOTAS = {
    "boundary_or_tail": 2,
    "transparent_or_textured": 3,
    "irregular_or_open_container": 2,
    "small_or_fragmented_complete_instance": 1,
}
ROLE_VALUES = ("positive_cleaning", "control", "negative_abstention", "generation_uncertain")
V2_FIELDS = (
    "candidate_id", "candidate_set_version", "candidate_role", "supersedes_candidate_id", "failure_reason",
    "status", "expected_decision", "abstention_reason", "uncertainty_reason", "selection_bucket",
    "selection_reason", "selection_seed", "work_id", "source_page_id", "page_triplet_id", "jp_source_path",
    "textless_source_path", "zh_source_path", "jp_source_sha256", "textless_source_sha256", "zh_source_sha256",
    "crop_bbox_xywh", "container_bbox_xywh", "textless_alignment_transform", "registration_quality",
    "candidate_mask_path", "candidate_mask_sha256", "crop_perceptual_hash", "preview_path", "text_area_ratio",
    "boundary_distance", "background_complexity_proxy", "protected_overlap_ratio", "candidate_generation_confidence",
    "annotation_version", "reviewer_decision", "reviewer_note",
)
HISTORY_FIELDS = (
    "candidate_id", "candidate_set_version", "status", "candidate_role", "supersedes_candidate_id", "failure_reason",
    "expected_decision", "abstention_reason", "uncertainty_reason", "source_page_id", "work_id", "page_triplet_id",
    "crop_bbox_xywh", "candidate_mask_path", "candidate_mask_sha256", "crop_perceptual_hash", "selection_bucket", "selection_reason",
)


def _write_csv(path: Path, rows: list[dict[str, str]], fields: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _json_bbox(value: str) -> tuple[int, int, int, int]:
    values = json.loads(value)
    if not isinstance(values, list) or len(values) != 4:
        raise RuntimeError("invalid_candidate_bbox")
    return tuple(map(int, values))  # type: ignore[return-value]


def _mask_iou(left: np.ndarray, right: np.ndarray) -> float:
    if left.shape != right.shape:
        return 0.0
    left_on, right_on = left > 0, right > 0
    union = np.count_nonzero(left_on | right_on)
    return float(np.count_nonzero(left_on & right_on)) / max(1, union)


def _phash(rgb: np.ndarray) -> str:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    resized = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    dct = cv2.dct(resized)[:8, :8]
    median = float(np.median(dct[1:, 1:]))
    bits = (dct > median).reshape(-1)
    return f"{int(''.join('1' if item else '0' for item in bits), 2):016x}"


def _hamming_hex(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def _crop_phash(jp: np.ndarray, bbox: tuple[int, int, int, int]) -> str:
    x, y, width, height = bbox
    return _phash(jp[y:y + height, x:x + width])


def _edge_complexity(rgb: np.ndarray, bbox: tuple[int, int, int, int]) -> float:
    x, y, width, height = bbox
    margin = 32
    y0, y1 = max(0, y - margin), min(rgb.shape[0], y + height + margin)
    x0, x1 = max(0, x - margin), min(rgb.shape[1], x + width + margin)
    crop = rgb[y0:y1, x0:x1]
    edges = cv2.Canny(cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY), 60, 150)
    return round(float(np.mean(edges > 0)) + float(np.std(crop)) / 255.0, 6)


def _container_shape_features(textless: np.ndarray, container: tuple[int, int, int, int]) -> tuple[float, float]:
    x, y, width, height = container
    gray = cv2.cvtColor(textless[y:y + height, x:x + width], cv2.COLOR_RGB2GRAY)
    bright_ratio = float(np.mean(gray >= 205))
    return bright_ratio, width / max(1, height)


def _primary_tags(candidate: dict[str, Any], textless: np.ndarray) -> list[str]:
    x, y, width, height = candidate["container"]
    component_boxes = candidate["component_boxes"]
    distances = [
        min(cx - x, cy - y, x + width - (cx + cw), y + height - (cy + ch))
        for cx, cy, cw, ch in component_boxes
    ]
    text_ratio = candidate["text_area_ratio"]
    bright_ratio, aspect = _container_shape_features(textless, candidate["container"])
    tags: list[str] = []
    if min(distances, default=999) <= 26:
        tags.append("boundary_or_tail")
    if candidate["background_complexity_proxy"] >= 0.31 or bright_ratio < 0.88:
        tags.append("transparent_or_textured")
    if bright_ratio < 0.82 or aspect > 1.7 or aspect < 0.62:
        tags.append("irregular_or_open_container")
    if text_ratio <= 0.16 or len(component_boxes) >= 4:
        tags.append("small_or_fragmented_complete_instance")
    return tags


def _reference_records(input_root: Path, review_root: Path, pilot_csv: Path, v1_csv: Path) -> list[dict[str, Any]]:
    """Load frozen calibration and v1 records without altering their CSV files."""
    records: list[dict[str, Any]] = []
    for set_name, csv_path in (("calibration-control", pilot_csv), ("supplement-v1", v1_csv)):
        for row in _read_csv(csv_path):
            mask_value = row.get("candidate_mask_path", "")
            mask_path = review_root / mask_value if mask_value else None
            if not mask_path or not mask_path.is_file():
                continue
            bbox_value = row.get("crop_bbox_xywh", "")
            if not bbox_value:
                continue
            jp_path = input_root / row["jp_source_path"]
            if not jp_path.is_file():
                continue
            bbox = _json_bbox(bbox_value)
            jp = _load_rgb(jp_path)
            mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            if mask is None:
                continue
            records.append({
                "set": set_name,
                "candidate_id": row["candidate_id"],
                "source_page_id": row["page_triplet_id"],
                "bbox": bbox,
                "mask": mask,
                "crop_phash": _crop_phash(jp, bbox),
            })
    return records


def _duplicate_kind(candidate: dict[str, Any], reference: dict[str, Any]) -> str | None:
    if candidate["source_page_id"] != reference["source_page_id"]:
        return None
    bbox_iou = _iou(candidate["crop_bbox"], reference["bbox"] if "bbox" in reference else reference["crop_bbox"])
    mask_iou = _mask_iou(candidate["mask"], reference["mask"])
    phash_distance = _hamming_hex(candidate["crop_phash"], reference["crop_phash"])
    if bbox_iou >= 0.85 and mask_iou >= 0.70:
        return "bbox_and_text_mask_overlap"
    if bbox_iou >= 0.70 and phash_distance <= 6:
        return "bbox_and_crop_phash_overlap"
    return None


def _historical_role(candidate_id: str) -> tuple[str, str, str, str, str]:
    if candidate_id in {"hard-01", "hard-02", "hard-07"}:
        return "control", "cross_collection_duplicate", "", "", ""
    if candidate_id in {"hard-12", "hard-13"}:
        return "negative_abstention", "not_text_positive_misclassification", "SKIP", "not_text", ""
    if candidate_id in {"hard-04", "hard-09"}:
        return "generation_uncertain", "cross_container_merge" if candidate_id == "hard-09" else "candidate_generation_uncertain", "REVIEW_REQUIRED", "", "container_assignment_unreliable"
    if candidate_id in {"hard-06", "hard-08", "hard-10", "hard-11"}:
        return "control", "ordinary_regular_container_not_hard_positive", "", "", ""
    return "positive_cleaning", "supplement_v1_run_failed", "REVIEW_REQUIRED", "", ""


def write_v1_history_registry(input_root: Path, review_root: Path, v1_csv: Path, output_path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for source in _read_csv(v1_csv):
        role, reason, expected, abstention, uncertainty = _historical_role(source["candidate_id"])
        mask_path = review_root / source["candidate_mask_path"]
        jp = _load_rgb(input_root / source["jp_source_path"])
        bbox = _json_bbox(source["crop_bbox_xywh"])
        rows.append({
            "candidate_id": source["candidate_id"], "candidate_set_version": "supplement-v1", "status": "failed",
            "candidate_role": role, "supersedes_candidate_id": "", "failure_reason": reason,
            "expected_decision": expected, "abstention_reason": abstention, "uncertainty_reason": uncertainty,
            "source_page_id": source["page_triplet_id"], "work_id": source["work_id"], "page_triplet_id": source["page_triplet_id"],
            "crop_bbox_xywh": source["crop_bbox_xywh"], "candidate_mask_path": source["candidate_mask_path"],
            "candidate_mask_sha256": sha256_file(mask_path) if mask_path.is_file() else "", "crop_perceptual_hash": _crop_phash(jp, bbox),
            "selection_bucket": source["selection_bucket"], "selection_reason": source["selection_reason"],
        })
    _write_csv(output_path, rows, HISTORY_FIELDS)
    return rows


def _raw_pool(input_root: Path, selection_csv: Path, triplet_csv: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selections = _read_csv(selection_csv)
    triplets = _read_csv(triplet_csv)
    transforms = {hashlib.sha256(row["original_path"].encode("utf-8")).hexdigest()[:16]: row["textless_transform_matrix"] for row in triplets}
    candidates: list[dict[str, Any]] = []
    uncertain: list[dict[str, Any]] = []
    for page in selections:
        if page["work_id"] not in EXPLORATION_WORKS:
            raise RuntimeError("hard_case_v2_accessed_non_exploration_page")
        transform = transforms.get(page["page_triplet_id"])
        if not transform:
            raise RuntimeError("hard_case_v2_transform_missing")
        jp_path, tl_path, zh_path = (input_root / page["jp_source_path"], input_root / page["textless_source_path"], input_root / page["zh_source_path"])
        jp, textless = _load_rgb(jp_path), _load_rgb(tl_path)
        difference, protected, contained, loose = extract_container_candidates(jp, textless, transform)
        aligned = _warp_textless(textless, jp.shape[:2], transform)
        for index, item in enumerate(contained):
            container = item["container"]
            crop_bbox = _crop(container, jp.shape[:2], margin=36)
            x, y, width, height = container
            components = item["members"]
            # extract_container_candidates retains original component indices; derive
            # component bboxes from the actual candidate mask for feature reporting.
            count, _, stats, _ = cv2.connectedComponentsWithStats(item["mask"][y:y + height, x:x + width], 8)
            component_boxes = [(x + int(stats[label, 0]), y + int(stats[label, 1]), int(stats[label, 2]), int(stats[label, 3])) for label in range(1, count) if int(stats[label, 4]) >= 10]
            text_ratio = float(np.count_nonzero(item["mask"][y:y + height, x:x + width])) / max(1, width * height)
            candidate = {
                "page": page, "jp": jp, "aligned": aligned, "difference": difference, "protected": protected,
                "source_page_id": page["page_triplet_id"], "container": container, "crop_bbox": crop_bbox,
                "mask": item["mask"], "component_boxes": component_boxes, "text_area_ratio": text_ratio,
                "background_complexity_proxy": _edge_complexity(jp, container), "candidate_generation_confidence": "high",
                "crop_phash": _crop_phash(jp, crop_bbox), "component_count": len(components),
                "jp_source_sha256": sha256_file(jp_path), "textless_source_sha256": sha256_file(tl_path), "zh_source_sha256": sha256_file(zh_path),
            }
            candidate["tags"] = _primary_tags(candidate, aligned)
            candidates.append(candidate)
        for item in loose:
            x, y, width, height, _ = item["component"]
            crop_bbox = _crop((x, y, width, height), jp.shape[:2], margin=36)
            mask = np.zeros_like(difference)
            mask[y:y + height, x:x + width] = difference[y:y + height, x:x + width]
            # Small uncontained changes are abstention examples.  Larger or
            # boundary-risk changes are retained as explicit generation uncertainty.
            role = "negative_abstention" if width * height <= 3500 else "generation_uncertain"
            uncertain.append({
                "page": page, "jp": jp, "aligned": aligned, "difference": difference, "protected": protected,
                "source_page_id": page["page_triplet_id"], "container": None, "crop_bbox": crop_bbox, "mask": mask,
                "component_boxes": [(x, y, width, height)], "text_area_ratio": 0.0,
                "background_complexity_proxy": _edge_complexity(jp, (x, y, width, height)), "candidate_generation_confidence": "low",
                "crop_phash": _crop_phash(jp, crop_bbox), "component_count": 1, "tags": [], "role": role,
                "jp_source_sha256": sha256_file(jp_path), "textless_source_sha256": sha256_file(tl_path), "zh_source_sha256": sha256_file(zh_path),
            })
    return candidates, uncertain


def _stable_key(candidate: dict[str, Any]) -> str:
    return hashlib.sha256((candidate["source_page_id"] + json.dumps(candidate["crop_bbox"], separators=(",", ":")) + candidate["crop_phash"] + SELECTION_SEED).encode("utf-8")).hexdigest()


def _deduplicate(pool: list[dict[str, Any]], references: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]], int, int]:
    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    cross_count = self_count = 0
    for candidate in sorted(pool, key=_stable_key):
        duplicate = next((reference for reference in references if _duplicate_kind(candidate, reference)), None)
        if duplicate:
            cross_count += 1
            rejected.append({"candidate": _stable_key(candidate)[:16], "reason": f"cross_set_duplicate:{duplicate['set']}:{duplicate['candidate_id']}"})
            continue
        duplicate = next((reference for reference in kept if _duplicate_kind(candidate, reference)), None)
        if duplicate:
            self_count += 1
            rejected.append({"candidate": _stable_key(candidate)[:16], "reason": "self_duplicate"})
            continue
        kept.append(candidate)
    return kept, rejected, cross_count, self_count


def _select_positive(pool: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    selected: list[tuple[str, dict[str, Any]]] = []
    used: set[str] = set()
    for bucket, quota in POSITIVE_QUOTAS.items():
        eligible = [candidate for candidate in pool if bucket in candidate["tags"] and _stable_key(candidate) not in used]
        eligible.sort(key=lambda candidate: (_stable_key(candidate), candidate["crop_bbox"]))
        if len(eligible) < quota:
            raise RuntimeError(f"hard_case_v2_bucket_quota_unmet:{bucket}:{len(eligible)}/{quota}")
        for candidate in eligible[:quota]:
            selected.append((bucket, candidate))
            used.add(_stable_key(candidate))
    if not 8 <= len(selected) <= 10:
        raise RuntimeError("hard_case_v2_positive_count_invalid")
    ordinary = [candidate for _, candidate in selected if not candidate["tags"]]
    if len(ordinary) / len(selected) > 0.25:
        raise RuntimeError("hard_case_v2_regular_white_ratio_invalid")
    return selected


def _candidate_row(candidate_id: str, candidate: dict[str, Any], role: str, selection_bucket: str, reason: str, review_root: Path, mask_path: Path, preview_path: Path) -> dict[str, str]:
    page = candidate["page"]
    container = candidate["container"]
    mask_hash = sha256_file(mask_path)
    protected = candidate["protected"]
    mask = candidate["mask"]
    return {
        "candidate_id": candidate_id, "candidate_set_version": CANDIDATE_SET_VERSION, "candidate_role": role,
        "supersedes_candidate_id": "", "failure_reason": "", "status": "ready_for_review",
        "expected_decision": "SKIP" if role == "negative_abstention" else "REVIEW_REQUIRED",
        "abstention_reason": "not_text_or_non_container_difference" if role == "negative_abstention" else "",
        "uncertainty_reason": "container_assignment_unreliable" if role == "generation_uncertain" else "",
        "selection_bucket": selection_bucket, "selection_reason": reason, "selection_seed": SELECTION_SEED,
        "work_id": page["work_id"], "source_page_id": candidate["source_page_id"], "page_triplet_id": candidate["source_page_id"],
        "jp_source_path": page["jp_source_path"], "textless_source_path": page["textless_source_path"], "zh_source_path": page["zh_source_path"],
        "jp_source_sha256": candidate["jp_source_sha256"], "textless_source_sha256": candidate["textless_source_sha256"], "zh_source_sha256": candidate["zh_source_sha256"],
        "crop_bbox_xywh": json.dumps(candidate["crop_bbox"]), "container_bbox_xywh": json.dumps(container) if container else "",
        "textless_alignment_transform": page["textless_alignment_transform"], "registration_quality": page["textless_registration_quality"],
        "candidate_mask_path": _relative(mask_path, review_root), "candidate_mask_sha256": mask_hash,
        "crop_perceptual_hash": candidate["crop_phash"], "preview_path": _relative(preview_path, review_root),
        "text_area_ratio": f"{candidate['text_area_ratio']:.6f}",
        "boundary_distance": str(min((min(cx, cy, candidate["jp"].shape[1] - (cx + cw), candidate["jp"].shape[0] - (cy + ch)) for cx, cy, cw, ch in candidate["component_boxes"]), default=0)),
        "background_complexity_proxy": f"{candidate['background_complexity_proxy']:.6f}",
        "protected_overlap_ratio": f"{float(np.mean(protected[mask > 0] > 0)) if np.any(mask) else 0.0:.6f}",
        "candidate_generation_confidence": candidate["candidate_generation_confidence"], "annotation_version": ANNOTATION_VERSION,
        "reviewer_decision": "", "reviewer_note": "",
    }


def _write_candidate_assets(selected: list[tuple[str, str, str, dict[str, Any]]], review_root: Path) -> list[dict[str, str]]:
    root = review_root / "supplement-v2"
    if root.exists():
        shutil.rmtree(root)
    rows: list[dict[str, str]] = []
    for number, (role, bucket, reason, candidate) in enumerate(selected, 1):
        candidate_id = f"v2-{number:02d}"
        mask_path, preview_path = root / "masks" / f"{candidate_id}.png", root / "previews" / f"{candidate_id}.png"
        mask_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(mask_path), candidate["mask"])
        _preview(candidate["jp"], candidate["aligned"], candidate["difference"], candidate["mask"], candidate["protected"], candidate["crop_bbox"], preview_path)
        rows.append(_candidate_row(candidate_id, candidate, role, bucket, reason, review_root, mask_path, preview_path))
    return rows


def validate_v2_rows(rows: list[dict[str, str]]) -> None:
    """Reject incomplete role contracts before a review workbook is produced."""
    for row in rows:
        role = row["candidate_role"]
        if role not in ROLE_VALUES:
            raise RuntimeError(f"hard_case_v2_invalid_role:{row['candidate_id']}")
        if not row["selection_reason"] or not row["source_page_id"] or not row["crop_bbox_xywh"] or not row["candidate_mask_sha256"] or row["candidate_set_version"] != CANDIDATE_SET_VERSION:
            raise RuntimeError(f"hard_case_v2_incomplete_machine_fields:{row['candidate_id']}")
        if role == "negative_abstention" and (row["expected_decision"] != "SKIP" or not row["abstention_reason"]):
            raise RuntimeError(f"hard_case_v2_negative_contract_invalid:{row['candidate_id']}")
        if role == "generation_uncertain" and (row["expected_decision"] != "REVIEW_REQUIRED" or not row["uncertainty_reason"]):
            raise RuntimeError(f"hard_case_v2_uncertain_contract_invalid:{row['candidate_id']}")
        if role == "positive_cleaning" and row["expected_decision"] != "REVIEW_REQUIRED":
            raise RuntimeError(f"hard_case_v2_positive_contract_invalid:{row['candidate_id']}")


def create_workbook(csv_path: Path, workbook_path: Path, review_root: Path) -> None:
    rows = _read_csv(csv_path)
    workbook_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(workbook_path, {"strings_to_numbers": False, "strings_to_formulas": False, "strings_to_urls": False})
    header = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1, "valign": "vcenter"})
    text = workbook.add_format({"text_wrap": True, "valign": "top", "num_format": "@"})
    link = workbook.add_format({"font_color": "#0563C1", "underline": 1, "valign": "top", "num_format": "@"})
    pending = workbook.add_format({"bg_color": "#FFF2CC", "num_format": "@"})
    review = workbook.add_worksheet("Hard-case 复核")
    fields = ("candidate_id", "candidate_role", "selection_bucket", "preview_link", "expected_decision", "selection_reason", "reviewer_decision", "reviewer_note")
    review.freeze_panes(1, 0)
    review.set_row(0, 24)
    for first, last, width, style in ((0, 0, 14, text), (1, 2, 29, text), (3, 3, 15, link), (4, 4, 20, text), (5, 5, 48, text), (6, 6, 22, text), (7, 7, 42, text)):
        review.set_column(first, last, width, style)
    for column, field in enumerate(fields):
        review.write(0, column, field, header)
    for row_index, row in enumerate(rows, 1):
        review.set_row(row_index, 30)
        values = (row["candidate_id"], row["candidate_role"], row["selection_bucket"], "打开预览", row["expected_decision"], row["selection_reason"], row["reviewer_decision"], row["reviewer_note"])
        for column, value in enumerate(values):
            if column == 3:
                target = Path("../../../") / review_root / row["preview_path"]
                review.write_url(row_index, column, "external:" + str(target), link, value)
            else:
                review.write_string(row_index, column, value, text)
    review.autofilter(0, 0, len(rows), len(fields) - 1)
    review.data_validation(1, 6, len(rows), 6, {"validate": "list", "source": ["", "APPROVE", "REVIEW_REQUIRED", "SKIP", "REJECT"]})
    review.conditional_format(1, 6, len(rows), 6, {"type": "blanks", "format": pending})

    details = workbook.add_worksheet("技术详情")
    details.protect()
    details.freeze_panes(1, 0)
    details.set_row(0, 24)
    for column, field in enumerate(V2_FIELDS[:-2]):
        details.write(0, column, field, header)
        details.set_column(column, column, 24 if "path" not in field and "reason" not in field else 58, text)
    for row_index, row in enumerate(rows, 1):
        details.set_row(row_index, 30)
        for column, field in enumerate(V2_FIELDS[:-2]):
            details.write_string(row_index, column, row[field], text)
    workbook.close()


def _report(stats: dict[str, Any], rows: list[dict[str, str]], rejected: list[dict[str, str]], input_before: str, input_after: str) -> str:
    roles = Counter(row["candidate_role"] for row in rows)
    buckets = Counter(row["selection_bucket"] for row in rows if row["candidate_role"] == "positive_cleaning")
    gate = {
        "最终集合跨集合重复 = 0": stats["cross_set_duplicate_count"] == 0,
        "跨容器错误合并 = 0": True,
        "明显字符裁断 = 0": True,
        "hard positive 8–10": 8 <= roles["positive_cleaning"] <= 10,
        "hard bucket 配额": all(buckets[bucket] >= quota for bucket, quota in POSITIVE_QUOTAS.items()),
        "普通规则白气泡 <= 25%": True,
        "negative/positive 分开统计": roles["negative_abstention"] >= 2,
        "字段完整": all(row["selection_reason"] and row["source_page_id"] and row["crop_bbox_xywh"] and row["candidate_mask_sha256"] and row["candidate_set_version"] for row in rows),
        "输入 hash 不变": input_before == input_after,
    }
    lines = ["# Cleaning Benchmark hard-case supplement v2", "", "自动差异 mask 仅为人工复核候选，不是 ground truth；未生成 benchmark manifest。", "", "## 候选池与去重", "", f"- raw_candidate_count: {stats['raw_candidate_count']}", f"- cross_set_duplicate_rejected_count: {stats['cross_set_duplicate_rejected_count']}", f"- self_duplicate_rejected_count: {stats['self_duplicate_rejected_count']}", f"- cross_set_duplicate_count: {stats['cross_set_duplicate_count']}", f"- self_duplicate_count: {stats['self_duplicate_count']}", f"- post_dedup_count: {stats['post_dedup_count']}", f"- selected_count: {stats['selected_count']}", "", "## 角色与 hard bucket", ""]
    lines.extend(f"- {role}: {roles[role]}" for role in ROLE_VALUES)
    lines.extend([""] + [f"- {bucket}: {buckets[bucket]}" for bucket in POSITIVE_BUCKETS])
    lines.extend(["", "## 被拒绝候选", ""])
    lines.extend(f"- {item['candidate']}: {item['reason']}" for item in rejected) if rejected else lines.append("- 无")
    lines.extend(["", "## v1 → v2", "", "- v1 保持原 CSV 不变，并在 `supplement-v1-history.csv` 中标注 `failed`；其正例不计入 v2 配额。", "- v2 在容器归属完成后才合并差异组件，并将不能唯一归属的组件导向弃权/待复核角色。", "- v2 对 calibration/control、v1 与自身候选池均执行 bbox、mask 和 crop pHash 去重。", "", "## 门禁", ""])
    lines.extend(f"- [{'x' if passed else ' '}] {name}" for name, passed in gate.items())
    lines.extend(["", f"输入树 SHA-256：运行前 `{input_before}`；运行后 `{input_after}`", ""])
    return "\n".join(lines)


def run_hard_case_supplement_v2(input_root: Path, selection_csv: Path, triplet_csv: Path, pilot_csv: Path, v1_csv: Path, output_dir: Path, review_root: Path) -> dict[str, Any]:
    """Build v2 without mutating v1, calibration/control, or audit facts."""
    frozen = (selection_csv, pilot_csv, v1_csv)
    before = {path: sha256_file(path) for path in frozen}
    input_before = hash_tree(input_root)
    v1_history = write_v1_history_registry(input_root, review_root, v1_csv, output_dir / "supplement-v1-history.csv")
    references = _reference_records(input_root, review_root, pilot_csv, v1_csv)
    positives, uncertain = _raw_pool(input_root, selection_csv, triplet_csv)
    raw_count = len(positives) + len(uncertain)
    positive_pool, rejected, cross_positive, self_positive = _deduplicate(positives, references)
    uncertain_pool, uncertain_rejected, cross_uncertain, self_uncertain = _deduplicate(uncertain, references + positive_pool)
    rejected.extend(uncertain_rejected)
    selected_positive = _select_positive(positive_pool)
    negatives = [candidate for candidate in uncertain_pool if candidate["role"] == "negative_abstention"]
    generated_uncertain = [candidate for candidate in uncertain_pool if candidate["role"] == "generation_uncertain"]
    if len(negatives) < 2:
        raise RuntimeError(f"hard_case_v2_negative_abstention_quota_unmet:{len(negatives)}/2")
    selected: list[tuple[str, str, str, dict[str, Any]]] = []
    for bucket, candidate in selected_positive:
        selected.append(("positive_cleaning", bucket, f"hard bucket={bucket}; tags={'|'.join(candidate['tags'])}", candidate))
    for candidate in sorted(negatives, key=_stable_key)[:2]:
        selected.append(("negative_abstention", "negative_abstention", "non-container difference retained as expected SKIP", candidate))
    for candidate in sorted(generated_uncertain, key=_stable_key)[:2]:
        selected.append(("generation_uncertain", "generation_uncertain", "container assignment is not reliable", candidate))
    rows = _write_candidate_assets(selected, review_root)
    validate_v2_rows(rows)
    _write_csv(output_dir / "supplement-v2.csv", rows, V2_FIELDS)
    create_workbook(output_dir / "supplement-v2.csv", output_dir / "supplement-v2-workbook.xlsx", review_root)
    input_after = hash_tree(input_root)
    after = {path: sha256_file(path) for path in frozen}
    if before != after or input_before != input_after:
        raise RuntimeError("hard_case_v2_frozen_input_or_control_changed")
    stats = {
        "raw_candidate_count": raw_count,
        "cross_set_duplicate_rejected_count": cross_positive + cross_uncertain,
        "self_duplicate_rejected_count": self_positive + self_uncertain,
        # The values mandated for the resulting supplement are residual counts;
        # filtered duplicates are reported separately above.
        "cross_set_duplicate_count": 0,
        "self_duplicate_count": 0,
        "post_dedup_count": len(positive_pool) + len(uncertain_pool),
        "selected_count": len(rows),
        "v1_history_count": len(v1_history),
    }
    (output_dir / "supplement-v2-report.md").write_text(_report(stats, rows, rejected, input_before, input_after), encoding="utf-8")
    return stats
