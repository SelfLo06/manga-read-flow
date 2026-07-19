"""Container-level, five-page candidate pilot; never regenerates region-review.csv."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import xlsxwriter

from .core import _labelled_strip, _load_rgb, _relative, _warp_textless, sha256_file


ANNOTATION_VERSION = "cleaning-benchmark-pilot-container-v0.1"
# The initial five-page proof slice deliberately uses the colour Exploration
# work.  The grayscale work's containers are not yet conservatively separable;
# its components must remain uncertain rather than being used to fill this pilot.
PILOT_PAGE_COUNTS = {"work-003": 5}
PILOT_FIELDS = (
    "candidate_id", "work_id", "page_triplet_id", "jp_source_path", "textless_source_path", "zh_source_path",
    "jp_source_sha256", "textless_source_sha256", "zh_source_sha256", "crop_bbox_xywh", "container_bbox_xywh",
    "textless_alignment_transform", "registration_quality", "candidate_mask_path", "candidate_mask_sha256", "preview_path",
    "candidate_unit", "candidate_generation_status", "uncertainty_reason", "selection_seed", "annotation_version",
    "page_role", "eligibility", "complexity_class", "mask_status", "protected_structure_status", "rejection_reason", "reviewer_note",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PILOT_FIELDS, extrasaction="raise")
        writer.writeheader(); writer.writerows(rows)
    temporary.replace(path)


def _boxes(mask: np.ndarray, min_area: int) -> list[tuple[int, int, int, int, int]]:
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    result = []
    for label in range(1, count):
        x, y, width, height, area = map(int, stats[label])
        if area >= min_area and width >= 2 and height >= 2:
            result.append((x, y, width, height, area))
    return result


def _text_containers(textless_gray: np.ndarray) -> list[tuple[int, int, int, int]]:
    # Bright enclosed regions are a conservative local proxy for speech bubbles
    # and white text boxes.  Large page background regions are explicitly excluded.
    bright = np.where(textless_gray >= 205, 255, 0).astype(np.uint8)
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
    page_area = bright.size
    containers = []
    for x, y, width, height, area in _boxes(bright, 900):
        if area <= page_area * .25 and width >= 28 and height >= 28:
            containers.append((x, y, width, height))
    return containers


def _inside(component: tuple[int, int, int, int, int], container: tuple[int, int, int, int]) -> bool:
    x, y, width, height, _ = component; cx, cy, cw, ch = container
    return x >= cx + 3 and y >= cy + 3 and x + width <= cx + cw - 3 and y + height <= cy + ch - 3


def _container_for_component(component: tuple[int, int, int, int, int], containers: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int] | None:
    """Return one *unambiguous* enclosing container, never a nearest container.

    Difference components are allowed to join only after this assignment.  This
    prevents a dilation radius from bridging two adjacent speech bubbles.
    """
    matches = [container for container in containers if _inside(component, container)]
    if len(matches) != 1:
        return None
    return matches[0]


def _iou(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
    x1, y1, w1, h1 = left; x2, y2, w2, h2 = right
    overlap = max(0, min(x1 + w1, x2 + w2) - max(x1, x2)) * max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
    return overlap / max(1, w1 * h1 + w2 * h2 - overlap)


def extract_container_candidates(jp_rgb: np.ndarray, textless_rgb: np.ndarray, transform: str) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]], list[dict[str, Any]]]:
    """Return ready container candidates and uncertain difference groups separately."""
    aligned = _warp_textless(textless_rgb, jp_rgb.shape[:2], transform)
    jp_gray, tl_gray = cv2.cvtColor(jp_rgb, cv2.COLOR_RGB2GRAY), cv2.cvtColor(aligned, cv2.COLOR_RGB2GRAY)
    diff = cv2.absdiff(jp_gray, tl_gray)
    threshold = max(18, int(np.percentile(diff, 90)))
    difference = np.where(diff >= threshold, 255, 0).astype(np.uint8)
    difference = cv2.dilate(difference, np.ones((3, 3), np.uint8), iterations=1)
    components = _boxes(difference, 10)
    containers = _text_containers(tl_gray)
    # Assign before merging.  A text container is the candidate unit: all
    # columns, punctuation, small glyphs and outlines inside it stay together,
    # while no component can cross into a neighbouring container.
    grouped_by_container: dict[tuple[int, int, int, int], list[int]] = defaultdict(list)
    uncertain: list[dict[str, Any]] = []
    page_height, page_width = difference.shape
    for index, component in enumerate(components):
        x, y, width, height, _ = component
        if x <= 12 or y <= 12 or x + width >= page_width - 12 or y + height >= page_height - 12:
            uncertain.append({"component": component, "reason": "candidate_generation_uncertain"})
            continue
        container = _container_for_component(component, containers)
        if container is None:
            uncertain.append({"component": component, "reason": "candidate_generation_uncertain"})
            continue
        grouped_by_container[container].append(index)

    grouped: list[dict[str, Any]] = []
    for container, members in grouped_by_container.items():
        x, y, width, height = container
        # Containers implausibly large for local text are not promoted to a
        # review candidate; their components remain explicitly uncertain.
        if width > page_width * .55 or height > page_height * .78:
            uncertain.extend({"component": components[index], "reason": "candidate_generation_uncertain"} for index in members)
            continue
        local = np.zeros_like(difference)
        local[y:y + height, x:x + width] = difference[y:y + height, x:x + width]
        grouped.append({"container": container, "unit_type": "text_container", "mask": local, "score": int(np.count_nonzero(local)), "members": members})
    grouped.sort(key=lambda item: (-item["score"], item["container"][1], item["container"][0]))
    deduped: list[dict[str, Any]] = []
    for item in grouped:
        if any(_iou(item["container"], prior["container"]) >= .85 for prior in deduped):
            continue
        deduped.append(item)
    protected = cv2.Canny(tl_gray, 60, 150)
    for item in deduped:
        x, y, width, height = item["container"]
        cv2.rectangle(protected, (x, y), (x + width - 1, y + height - 1), 255, 2)
    return difference, protected, deduped, uncertain


def _crop(container: tuple[int, int, int, int], shape: tuple[int, int], margin: int = 28) -> tuple[int, int, int, int]:
    x, y, width, height = container; page_height, page_width = shape
    return max(0, x - margin), max(0, y - margin), min(page_width, x + width + margin) - max(0, x - margin), min(page_height, y + height + margin) - max(0, y - margin)


def _preview(jp: np.ndarray, textless: np.ndarray, difference: np.ndarray, mask: np.ndarray, protected: np.ndarray, bbox: tuple[int, int, int, int], output: Path) -> None:
    x, y, width, height = bbox
    diff_rgb, mask_rgb, protected_rgb = cv2.cvtColor(difference, cv2.COLOR_GRAY2RGB), np.full_like(jp, 255), textless.copy()
    mask_rgb[mask > 0] = (230, 40, 40); protected_rgb[protected > 0] = (40, 100, 230)
    _labelled_strip([("jp container crop", jp[y:y + height, x:x + width]), ("textless crop", textless[y:y + height, x:x + width]), ("difference", diff_rgb[y:y + height, x:x + width]), ("candidate text mask", mask_rgb[y:y + height, x:x + width]), ("protected container", protected_rgb[y:y + height, x:x + width])], output)


def _pilot_pages(selection_csv: Path) -> list[dict[str, str]]:
    selected = _read_csv(selection_csv)
    result = []
    for work_id, count in PILOT_PAGE_COUNTS.items():
        rows = [row for row in selected if row["work_id"] == work_id]
        rows.sort(key=lambda row: hashlib.sha256((row["page_triplet_id"] + row["selection_seed"]).encode()).hexdigest())
        result.extend(rows[:count])
    return result


def run_region_candidate_pilot(input_root: Path, selection_csv: Path, triplet_csv: Path, output_csv: Path, review_root: Path) -> dict[str, int]:
    pages = _pilot_pages(selection_csv)
    if len(pages) != 5:
        raise RuntimeError("region_candidate_pilot_requires_five_exploration_pages")
    triplets = _read_csv(triplet_csv)
    transforms = {hashlib.sha256(row["original_path"].encode("utf-8")).hexdigest()[:16]: row["textless_transform_matrix"] for row in triplets}
    if any(page["page_triplet_id"] not in transforms for page in pages):
        raise RuntimeError("pilot_page_transform_missing_from_frozen_triplet_quality")
    root = review_root / "region-candidate-pilot"
    if root.exists(): shutil.rmtree(root)
    rows: list[dict[str, str]] = []
    for page_index, page in enumerate(pages, 1):
        jp_path, tl_path, zh_path = (input_root / page["jp_source_path"], input_root / page["textless_source_path"], input_root / page["zh_source_path"])
        jp, textless = _load_rgb(jp_path), _load_rgb(tl_path)
        transform = transforms[page["page_triplet_id"]]
        difference, protected, candidates, uncertain = extract_container_candidates(jp, textless, transform)
        for index, candidate in enumerate(candidates[:2], 1):
            candidate_id = f"pilot-{page_index:02d}-{index:02d}"; bbox = _crop(candidate["container"], jp.shape[:2])
            mask_path, preview_path = root / "masks" / f"{candidate_id}.png", root / "previews" / f"{candidate_id}.png"
            mask_path.parent.mkdir(parents=True, exist_ok=True); cv2.imwrite(str(mask_path), candidate["mask"])
            _preview(jp, _warp_textless(textless, jp.shape[:2], transform), difference, candidate["mask"], protected, bbox, preview_path)
            rows.append({"candidate_id":candidate_id,"work_id":page["work_id"],"page_triplet_id":page["page_triplet_id"],"jp_source_path":page["jp_source_path"],"textless_source_path":page["textless_source_path"],"zh_source_path":page["zh_source_path"],"jp_source_sha256":sha256_file(jp_path),"textless_source_sha256":sha256_file(tl_path),"zh_source_sha256":sha256_file(zh_path),"crop_bbox_xywh":json.dumps(bbox),"container_bbox_xywh":json.dumps(candidate["container"]),"textless_alignment_transform":transform,"registration_quality":page["textless_registration_quality"],"candidate_mask_path":_relative(mask_path,review_root),"candidate_mask_sha256":sha256_file(mask_path),"preview_path":_relative(preview_path,review_root),"candidate_unit":candidate["unit_type"],"candidate_generation_status":"ready_for_review","uncertainty_reason":"","selection_seed":page["selection_seed"],"annotation_version":ANNOTATION_VERSION,"page_role":"","eligibility":"pending","complexity_class":"","mask_status":"","protected_structure_status":"","rejection_reason":"","reviewer_note":""})
        for index, item in enumerate(uncertain, 1):
            x,y,w,h,_=item["component"]
            rows.append({"candidate_id":f"uncertain-{page_index:02d}-{index:02d}","work_id":page["work_id"],"page_triplet_id":page["page_triplet_id"],"jp_source_path":page["jp_source_path"],"textless_source_path":page["textless_source_path"],"zh_source_path":page["zh_source_path"],"jp_source_sha256":sha256_file(jp_path),"textless_source_sha256":sha256_file(tl_path),"zh_source_sha256":sha256_file(zh_path),"crop_bbox_xywh":json.dumps(_crop((x,y,w,h),jp.shape[:2])),"container_bbox_xywh":"","textless_alignment_transform":transform,"registration_quality":page["textless_registration_quality"],"candidate_mask_path":"","candidate_mask_sha256":"","preview_path":"","candidate_unit":"unresolved_difference_component","candidate_generation_status":"candidate_generation_uncertain","uncertainty_reason":item["reason"],"selection_seed":page["selection_seed"],"annotation_version":ANNOTATION_VERSION,"page_role":"","eligibility":"pending","complexity_class":"","mask_status":"","protected_structure_status":"","rejection_reason":"","reviewer_note":""})
    ready = [row for row in rows if row["candidate_generation_status"] == "ready_for_review"]
    if not 10 <= len(ready) <= 15: raise RuntimeError(f"pilot_ready_candidate_count_outside_target:{len(ready)}")
    _write_csv(output_csv, rows)
    return {"pages":len(pages),"ready":len(ready),"uncertain":len(rows)-len(ready)}


def create_region_candidate_pilot_workbook(csv_path: Path, workbook_path: Path, review_root: Path) -> None:
    rows = [row for row in _read_csv(csv_path) if row["candidate_generation_status"] == "ready_for_review"]
    workbook = xlsxwriter.Workbook(workbook_path,{"strings_to_numbers":False,"strings_to_formulas":False,"strings_to_urls":False}); header=workbook.add_format({"bold":True,"bg_color":"#D9EAF7"}); text=workbook.add_format({"text_wrap":True,"valign":"top","num_format":"@"}); link=workbook.add_format({"font_color":"#0563C1","underline":1,"num_format":"@"})
    sheet=workbook.add_worksheet("区域候选复核"); fields=("candidate_id","work_id","page_triplet_id","preview_link","page_role","eligibility","complexity_class","mask_status","protected_structure_status","rejection_reason","reviewer_note")
    sheet.freeze_panes(1,0); sheet.set_row(0,24); sheet.set_column(0,0,16,text); sheet.set_column(1,2,18,text); sheet.set_column(3,3,15,link); sheet.set_column(4,9,23,text); sheet.set_column(10,10,42,text)
    for col,field in enumerate(fields):sheet.write(0,col,field,header)
    for i,row in enumerate(rows,1):
        sheet.set_row(i,30)
        for col,value in enumerate((row["candidate_id"],row["work_id"],row["page_triplet_id"],"打开预览",row["page_role"],row["eligibility"],row["complexity_class"],row["mask_status"],row["protected_structure_status"],row["rejection_reason"],row["reviewer_note"])):
            if col==3: sheet.write_url(i,col,"external:"+str(Path("../../../")/review_root/row["preview_path"]),link,value)
            else: sheet.write_string(i,col,value,text)
    sheet.autofilter(0,0,len(rows),len(fields)-1); workbook.close()
