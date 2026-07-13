#!/usr/bin/env python3
"""Local-only validation of restricted fill on manually annotated real bubbles.

The annotation table is intentionally static.  It is a one-time transcription of
reviewed glyph cells and bubble interiors; this tool does not detect text or
bubbles and never writes a source image.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "local_samples/cleaning/real_bubble_fill"
MANIFEST_PATH = DATA_DIR / "manifest.json"
MASK_DIR = DATA_DIR / "masks"
RATINGS_DIR = DATA_DIR / "ratings"
RATINGS_PATH = RATINGS_DIR / "ratings.csv"
OUTPUT_ROOT = ROOT / "local_samples/spike_outputs/cleaning-real-bubble-fill"
REAL_DIR = ROOT / "local_samples/real"
FONT = ImageFont.load_default()
RATING_VALUES = {"ACCEPTABLE", "REVIEW", "UNUSABLE"}


# Every glyph_box and allowed shape below was selected on the original page at
# 100% zoom.  Glyph pixels are rasterised only within these human-selected cells;
# the runtime never derives a mask from a page or a text detector.
ANNOTATIONS: list[dict[str, Any]] = [
    {"fixture_id": "black2-top-right", "source": "black2.webp", "fixture_class": "A", "expected_policy": "AUTO_FILL", "region_bbox": [830, 70, 330, 320], "glyph_boxes": [[925, 120, 115, 225]], "allowed": ["ellipse", 875, 95, 1080, 365], "ink": "dark", "risk_tags": [], "selection_rationale": "独立白色椭圆气泡，文字与轮廓、尾巴保持距离。"},
    {"fixture_id": "black2-middle-right", "source": "black2.webp", "fixture_class": "A", "expected_policy": "AUTO_FILL", "region_bbox": [870, 385, 315, 430], "glyph_boxes": [[950, 445, 140, 290]], "allowed": ["ellipse", 895, 410, 1140, 790], "ink": "dark", "risk_tags": [], "selection_rationale": "大白色气泡内部平坦，文字未接触边界。"},
    {"fixture_id": "black2-lower-left", "source": "black2.webp", "fixture_class": "A", "expected_policy": "AUTO_FILL", "region_bbox": [55, 1005, 315, 320], "glyph_boxes": [[125, 1040, 140, 225]], "allowed": ["ellipse", 85, 1020, 335, 1285], "ink": "dark", "risk_tags": [], "selection_rationale": "左下独立气泡，留有完整内侧保护带。"},
    {"fixture_id": "black1-bottom-right", "source": "black1.webp", "fixture_class": "A", "expected_policy": "AUTO_FILL", "region_bbox": [885, 1180, 350, 350], "glyph_boxes": [[960, 1245, 180, 210]], "allowed": ["polygon", [[935, 1215], [1165, 1195], [1210, 1425], [1135, 1505], [955, 1475]]], "ink": "dark", "risk_tags": [], "selection_rationale": "普通白色对白框；文本位于内侧，远离尾巴。"},
    {"fixture_id": "black1-top-right-sensitive", "source": "black1.webp", "fixture_class": "B", "expected_policy": "REVIEW_REQUIRED", "region_bbox": [850, 350, 385, 420], "glyph_boxes": [[920, 410, 235, 255]], "allowed": ["polygon", [[900, 390], [1165, 350], [1235, 440], [1210, 650], [1065, 710], [910, 660]]], "ink": "dark", "risk_tags": ["irregular_bubble", "near_tail"], "selection_rationale": "不规则对白框且靠近尖角/尾巴，作为 review 边界样本。"},
    {"fixture_id": "black1-music-note", "source": "black1.webp", "fixture_class": "D", "expected_policy": "SKIP", "region_bbox": [55, 400, 200, 310], "glyph_boxes": [], "allowed": None, "ink": "dark", "risk_tags": ["artistic_symbol", "non_dialogue"], "skip_reason": "音乐符号不是普通对白文字，禁止自动清除。", "selection_rationale": "艺术符号 SKIP control。"},
    {"fixture_id": "gura-top-dialogue", "source": "gura.webp", "fixture_class": "A", "expected_policy": "AUTO_FILL", "region_bbox": [145, 65, 185, 295], "glyph_boxes": [[205, 130, 90, 155]], "allowed": ["ellipse", 175, 85, 315, 335], "ink": "dark", "risk_tags": [], "selection_rationale": "顶部视频面板内的独立白色椭圆对白气泡。"},
    {"fixture_id": "gura-middle-right-sensitive", "source": "gura.webp", "fixture_class": "B", "expected_policy": "REVIEW_REQUIRED", "region_bbox": [565, 395, 185, 345], "glyph_boxes": [[610, 445, 85, 230]], "allowed": ["ellipse", 585, 415, 720, 715], "ink": "dark", "risk_tags": ["panel_proximity", "irregular_bubble"], "selection_rationale": "不规则轮廓且邻近视频面板结构，必须 review。"},
    {"fixture_id": "gura-rec-overlay", "source": "gura.webp", "fixture_class": "D", "expected_policy": "SKIP", "region_bbox": [625, 90, 125, 95], "glyph_boxes": [], "allowed": None, "ink": "dark", "risk_tags": ["ui_overlay", "panel_structure"], "skip_reason": "REC/时间码 UI overlay，禁止生成清字候选。", "selection_rationale": "UI overlay SKIP control。"},
    {"fixture_id": "gura-color-small-center", "source": "gura_color.webp", "fixture_class": "A", "expected_policy": "AUTO_FILL", "region_bbox": [355, 430, 165, 255], "glyph_boxes": [[400, 475, 75, 145]], "allowed": ["ellipse", 378, 450, 490, 655], "ink": "orange", "risk_tags": [], "selection_rationale": "白色小气泡，橙色文字与边框分离。"},
    {"fixture_id": "gura-color-small-right", "source": "gura_color.webp", "fixture_class": "A", "expected_policy": "AUTO_FILL", "region_bbox": [805, 685, 145, 210], "glyph_boxes": [[862, 745, 45, 90]], "allowed": ["ellipse", 850, 720, 915, 850], "ink": "orange", "risk_tags": [], "selection_rationale": "白色小气泡；审查后收紧至气泡内侧，排除左侧手部和背景。"},
    {"fixture_id": "gura-color-lower-left", "source": "gura_color.webp", "fixture_class": "A", "expected_policy": "AUTO_FILL", "region_bbox": [125, 1030, 300, 390], "glyph_boxes": [[190, 1080, 155, 260]], "allowed": ["polygon", [[175, 1055], [370, 1065], [415, 1160], [385, 1360], [255, 1400], [160, 1310]]], "ink": "blue", "risk_tags": [], "selection_rationale": "大白色气泡中蓝色竖排文字，内侧保留了较宽边界带。"},
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def safe(path: Path, root: Path = ROOT) -> Path:
    resolved, base = path.resolve(), root.resolve()
    if os.path.commonpath((str(resolved), str(base))) != str(base):
        raise ValueError(f"path escapes repository: {path}")
    return resolved


def image(path: Path) -> np.ndarray:
    value = cv2.imread(str(safe(path)), cv2.IMREAD_COLOR)
    if value is None:
        raise ValueError(f"cannot read image: {path}")
    return value


def source_path(fixture: dict[str, Any]) -> Path:
    return safe(REAL_DIR / fixture["source_image"])


def mask_path(kind: str, fixture: dict[str, Any]) -> Path:
    return safe(MASK_DIR / kind / f"{fixture['fixture_id']}.png", DATA_DIR)


def load_mask(kind: str, fixture: dict[str, Any]) -> np.ndarray:
    value = cv2.imread(str(mask_path(kind, fixture)), cv2.IMREAD_GRAYSCALE)
    if value is None:
        raise ValueError(f"missing {kind} mask for {fixture['fixture_id']}")
    return np.where(value > 127, 255, 0).astype(np.uint8)


def draw_allowed(shape: tuple[int, int], spec: list[Any] | None) -> np.ndarray:
    canvas = np.zeros(shape, dtype=np.uint8)
    if spec is None:
        return canvas
    if spec[0] == "ellipse":
        _, x1, y1, x2, y2 = spec
        cv2.ellipse(canvas, ((x1 + x2) // 2, (y1 + y2) // 2), ((x2 - x1) // 2, (y2 - y1) // 2), 0, 0, 360, 255, -1)
    elif spec[0] == "polygon":
        cv2.fillPoly(canvas, [np.array(spec[1], dtype=np.int32)], 255)
    else:
        raise ValueError(f"unknown allowed geometry: {spec[0]}")
    return canvas


def ink_mask(source: np.ndarray, boxes: list[list[int]], ink: str) -> np.ndarray:
    """Rasterise authored glyph cells; no page-level detection or proposal occurs."""
    mask = np.zeros(source.shape[:2], dtype=np.uint8)
    hsv = cv2.cvtColor(source, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)
    for x, y, width, height in boxes:
        roi = np.zeros_like(mask)
        roi[y:y + height, x:x + width] = 255
        if ink == "dark":
            selected = (gray < 180)
        elif ink == "orange":
            # Orange glyphs: red-dominant, saturated pixels inside the manually
            # selected glyph cells; white bubble and skin tones stay excluded.
            b, g, r = cv2.split(source)
            selected = (r > 100) & (r > g + 5) & (r > b + 15) & (hsv[:, :, 1] > 15)
        elif ink == "blue":
            b, g, r = cv2.split(source)
            selected = (b > r + 10) & (b > g * 0.72) & (hsv[:, :, 1] > 20)
        else:
            raise ValueError(f"unknown ink profile: {ink}")
        mask[(roi > 0) & selected] = 255
    # A single-pixel glyph-boundary expansion is part of the reviewed text mask
    # (not a detector). It captures compression/anti-alias pixels while retaining
    # the glyph contours rather than turning a text cell into a rectangle.
    return cv2.dilate(cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8)), np.ones((3, 3), np.uint8), iterations=1)


def materialize_annotations() -> None:
    """Write reviewed, static annotation assets.  This is not mask detection."""
    prior = load_manifest() if MANIFEST_PATH.exists() else {}
    if prior.get("freeze", {}).get("state") == "FROZEN":
        raise ValueError("inputs are frozen; refuse to materialize masks")
    for kind in ("text", "allowed", "protected"):
        (MASK_DIR / kind).mkdir(parents=True, exist_ok=True)
    fixtures: list[dict[str, Any]] = []
    for annotation in ANNOTATIONS:
        source = image(REAL_DIR / annotation["source"])
        height, width = source.shape[:2]
        fixture = {
            "fixture_id": annotation["fixture_id"], "source_image": annotation["source"],
            "region_bbox": dict(zip(("x", "y", "width", "height"), annotation["region_bbox"])),
            "fixture_class": annotation["fixture_class"], "expected_policy": annotation["expected_policy"],
            "text_mask": f"masks/text/{annotation['fixture_id']}.png" if annotation["fixture_class"] != "D" else None,
            "allowed_edit_mask": f"masks/allowed/{annotation['fixture_id']}.png" if annotation["fixture_class"] != "D" else None,
            "protected_mask": f"masks/protected/{annotation['fixture_id']}.png",
            "risk_tags": annotation["risk_tags"], "selection_rationale": annotation["selection_rationale"],
            "mask_review": "VALID", "mask_annotation_method": "human-selected glyph cells and bubble-interior geometry",
        }
        if annotation["fixture_class"] == "D":
            fixture["skip_reason"] = annotation["skip_reason"]
            protected = np.full((height, width), 255, dtype=np.uint8)
            cv2.imwrite(str(mask_path("protected", fixture)), protected)
        else:
            allowed = draw_allowed((height, width), annotation["allowed"])
            text = ink_mask(source, annotation["glyph_boxes"], annotation["ink"])
            # A hard containment guard prevents authored cells from escaping the
            # manually approved bubble interior.
            # Keep one explicit editable-pixel buffer.  d1 may consume this
            # buffer, but neither the authored glyph mask nor d0 may touch the
            # protected region.
            text[cv2.erode(allowed, np.ones((3, 3), np.uint8), iterations=1) == 0] = 0
            protected = cv2.bitwise_not(allowed)
            cv2.imwrite(str(mask_path("text", fixture)), text)
            cv2.imwrite(str(mask_path("allowed", fixture)), allowed)
            cv2.imwrite(str(mask_path("protected", fixture)), protected)
        fixtures.append(fixture)
    manifest = {"schema_version": 1, "spike": "real-bubble-fill-followup", "fixtures": fixtures, "freeze": {"state": "PREPARED_NOT_FROZEN"}, "materialization": "Static reviewed annotations only; no detector or auto-mask generator was run."}
    if prior.get("freeze_history"):
        manifest["freeze_history"] = prior["freeze_history"]
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("materialized 12 static reviewed fixture annotations")


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.is_file():
        raise ValueError("manifest missing; run materialize-annotations once")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def bbox(fixture: dict[str, Any]) -> tuple[int, int, int, int]:
    data = fixture["region_bbox"]
    return data["x"], data["y"], data["width"], data["height"]


def crop(source: np.ndarray, fixture: dict[str, Any], padding: int = 20) -> tuple[np.ndarray, tuple[int, int]]:
    x, y, width, height = bbox(fixture)
    top, left = max(0, y - padding), max(0, x - padding)
    bottom, right = min(source.shape[0], y + height + padding), min(source.shape[1], x + width + padding)
    return source[top:bottom, left:right], (left, top)


def valid_bbox(fixture: dict[str, Any], shape: tuple[int, int]) -> bool:
    x, y, width, height = bbox(fixture)
    return width > 0 and height > 0 and x >= 0 and y >= 0 and x + width <= shape[1] and y + height <= shape[0]


def is_binary(mask: np.ndarray) -> bool:
    return set(np.unique(mask)).issubset({0, 255})


def mask_stats(fixture: dict[str, Any]) -> dict[str, Any]:
    source = image(source_path(fixture))
    if not valid_bbox(fixture, source.shape[:2]):
        raise ValueError(f"invalid bbox: {fixture['fixture_id']}")
    protected = load_mask("protected", fixture)
    if protected.shape != source.shape[:2] or not is_binary(protected):
        raise ValueError(f"invalid protected mask: {fixture['fixture_id']}")
    result: dict[str, Any] = {"protected_area": int(np.count_nonzero(protected))}
    if fixture["fixture_class"] == "D":
        return result
    text, allowed = load_mask("text", fixture), load_mask("allowed", fixture)
    if text.shape != source.shape[:2] or allowed.shape != source.shape[:2] or not is_binary(text) or not is_binary(allowed):
        raise ValueError(f"invalid mask dimensions or values: {fixture['fixture_id']}")
    if not np.any(text) or np.any((text > 0) & (allowed == 0)) or np.any((text > 0) & (protected > 0)) or np.any((allowed > 0) & (protected > 0)):
        raise ValueError(f"invalid mask relation: {fixture['fixture_id']}")
    x, y, width, height = bbox(fixture)
    text_crop = text[y:y + height, x:x + width]
    ratio = float(np.count_nonzero(text_crop) / (width * height))
    if ratio > 0.45:
        raise ValueError(f"rectangle-like text mask: {fixture['fixture_id']}")
    # A fully-filled bounding rectangle is unambiguously an invalid bbox mask.
    ys, xs = np.where(text > 0)
    if xs.size:
        rect_ratio = xs.size / ((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1))
        if rect_ratio > 0.72:
            raise ValueError(f"solid rectangular text mask: {fixture['fixture_id']}")
    distance = cv2.distanceTransform((protected == 0).astype(np.uint8), cv2.DIST_L2, 3)
    min_distance = float(distance[text > 0].min()) if np.any(text) else 0.0
    if min_distance < 1:
        raise ValueError(f"text touches protected region: {fixture['fixture_id']}")
    result.update({"text_mask_area": int(np.count_nonzero(text)), "allowed_edit_area": int(np.count_nonzero(allowed)), "mask_to_bbox_ratio": ratio, "mask_to_allowed_ratio": float(np.count_nonzero(text) / np.count_nonzero(allowed)), "minimum_distance_to_protected_region": min_distance})
    return result


def input_records(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = {}
    for fixture in manifest["fixtures"]:
        stats = mask_stats(fixture)
        record = {"source_hash": sha256(source_path(fixture)), "protected_mask_hash": sha256(mask_path("protected", fixture)), **stats}
        if fixture["fixture_class"] != "D":
            record.update({"text_mask_hash": sha256(mask_path("text", fixture)), "allowed_mask_hash": sha256(mask_path("allowed", fixture))})
        records[fixture["fixture_id"]] = record
    return records


def validate() -> None:
    manifest = load_manifest()
    fixtures = manifest["fixtures"]
    ids = [item["fixture_id"] for item in fixtures]
    classes = Counter(item["fixture_class"] for item in fixtures)
    if len(fixtures) != 12 or len(ids) != len(set(ids)) or classes != Counter({"A": 8, "B": 2, "D": 2}):
        raise ValueError("fixture distribution must be exactly 8 A / 2 B / 2 D")
    pages = Counter(item["source_image"] for item in fixtures)
    required = {"black1.webp", "black2.webp", "gura.webp", "gura_color.webp"}
    if set(pages) != required or max(pages.values()) > 4:
        raise ValueError("all four real pages, at most four fixtures each, are required")
    if len({item["source_image"] for item in fixtures if item["fixture_class"] == "A"}) < 2:
        raise ValueError("A fixtures must not be concentrated on one page")
    records = input_records(manifest)
    freeze = manifest.get("freeze", {})
    if freeze.get("state") == "FROZEN":
        if records != freeze.get("records") or canonical_hash(fixtures) != freeze.get("fixture_set_sha256"):
            raise ValueError("frozen inputs changed")
    print(json.dumps({"valid": True, "fixtures": len(fixtures), "classes": classes, "freeze": freeze.get("state"), "records": records}, ensure_ascii=False, indent=2))


def rgb(value: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(value, cv2.COLOR_BGR2RGB))


def label(canvas: Image.Image, title: str) -> Image.Image:
    out = Image.new("RGB", (canvas.width, canvas.height + 22), "white")
    out.paste(canvas, (0, 22))
    ImageDraw.Draw(out).text((4, 4), title, fill="black", font=FONT)
    return out


def tile(items: list[Image.Image], columns: int = 3) -> Image.Image:
    width = max(item.width for item in items)
    height = max(item.height for item in items)
    out = Image.new("RGB", (width * columns, height * ((len(items) + columns - 1) // columns)), "white")
    for index, item in enumerate(items):
        out.paste(item, ((index % columns) * width, (index // columns) * height))
    return out


def overlay_masks(source: np.ndarray, text: np.ndarray | None, allowed: np.ndarray | None, protected: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    text_overlay, ap_overlay, combined = source.copy(), source.copy(), source.copy()
    if text is not None:
        text_overlay[text > 0] = (0, 0, 255)
        combined[text > 0] = (0, 0, 255)
    if allowed is not None:
        ap_overlay[allowed > 0] = cv2.addWeighted(ap_overlay, 0.45, np.full_like(ap_overlay, (0, 255, 0)), 0.55, 0)[allowed > 0]
        combined[allowed > 0] = cv2.addWeighted(combined, 0.60, np.full_like(combined, (0, 255, 0)), 0.40, 0)[allowed > 0]
    ap_overlay[protected > 0] = cv2.addWeighted(ap_overlay, 0.60, np.full_like(ap_overlay, (255, 0, 0)), 0.40, 0)[protected > 0]
    boundary = cv2.morphologyEx(protected, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    combined[boundary > 0] = (255, 255, 0)
    return text_overlay, ap_overlay, combined


def preview() -> None:
    manifest = load_manifest(); input_records(manifest)
    preview_dir = DATA_DIR / "previews"; review_dir = preview_dir / "mask-review"; review_dir.mkdir(parents=True, exist_ok=True)
    pages: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fixture in manifest["fixtures"]: pages[fixture["source_image"]].append(fixture)
    for page, fixtures in pages.items():
        source = image(REAL_DIR / page); annotated = source.copy()
        for fixture in fixtures:
            x, y, width, height = bbox(fixture); cv2.rectangle(annotated, (x, y), (x + width, y + height), (0, 0, 255), 3)
            cv2.putText(annotated, fixture["fixture_id"], (x, max(18, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1, cv2.LINE_AA)
        rgb(annotated).save(preview_dir / f"selection-{Path(page).stem}.png")
    for fixture in manifest["fixtures"]:
        source = image(source_path(fixture)); protected = load_mask("protected", fixture)
        text = allowed = None
        if fixture["fixture_class"] != "D": text, allowed = load_mask("text", fixture), load_mask("allowed", fixture)
        panels = overlay_masks(source, text, allowed, protected)
        items = []
        for title, frame in zip(("source crop", "text-mask overlay", "allowed/protected overlay", "combined boundary overlay"), (source, *panels)):
            frame_crop, _ = crop(frame, fixture); items.append(label(rgb(frame_crop), title))
        tile(items, 2).save(review_dir / f"{fixture['fixture_id']}.png")
    print(f"wrote selection and 12 mask-review images to {preview_dir.relative_to(ROOT)}")


def freeze() -> None:
    manifest = load_manifest()
    if manifest.get("freeze", {}).get("state") == "FROZEN": raise ValueError("already frozen")
    records = input_records(manifest)
    if any(item.get("mask_review") != "VALID" for item in manifest["fixtures"]): raise ValueError("all fixture mask reviews must be VALID")
    fixture_set = canonical_hash(manifest["fixtures"])
    manifest["freeze"] = {"state": "FROZEN", "frozen_at": datetime.now(timezone.utc).isoformat(), "git_head": git_head(), "fixture_set_sha256": fixture_set, "source_set_sha256": canonical_hash({key: value["source_hash"] for key, value in records.items()}), "text_mask_set_sha256": canonical_hash({key: value.get("text_mask_hash") for key, value in records.items()}), "allowed_mask_set_sha256": canonical_hash({key: value.get("allowed_mask_hash") for key, value in records.items()}), "protected_mask_set_sha256": canonical_hash({key: value["protected_mask_hash"] for key, value in records.items()}), "records": records}
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["freeze"], ensure_ascii=False, indent=2))


def supersede_mask_freeze() -> None:
    """Invalidate an evidence run before correcting an admitted mask failure."""
    manifest = load_manifest()
    if manifest.get("freeze", {}).get("state") != "FROZEN":
        raise ValueError("only frozen inputs can be superseded")
    previous = manifest["freeze"]
    run_dir = latest_run_dir()
    metadata_path = run_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["valid_for_verdict"] = False
    metadata["invalidation_reason"] = "visual review found glyph-mask undercoverage; preserved before mask correction"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    archive = DATA_DIR / "masks-history" / previous["text_mask_set_sha256"][:12]
    if archive.exists():
        raise ValueError(f"mask archive already exists: {archive}")
    shutil.copytree(MASK_DIR, archive)
    history = manifest.setdefault("freeze_history", [])
    history.append({"state": "SUPERSEDED_BEFORE_VERDICT", "reason": metadata["invalidation_reason"], "freeze": previous, "mask_archive": str(archive.relative_to(DATA_DIR)), "invalid_run": run_dir.name})
    manifest["freeze"] = {"state": "PREPARED_NOT_FROZEN", "supersedes": previous["fixture_set_sha256"][:12]}
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"invalidated {run_dir.name}; archived masks to {archive.relative_to(ROOT)}")


def git_head() -> str:
    import subprocess
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def latest_run_dir() -> Path:
    if not OUTPUT_ROOT.exists(): raise ValueError("no run output")
    runs = sorted(path for path in OUTPUT_ROOT.iterdir() if path.is_dir() and (path / "metadata.json").is_file())
    if not runs: raise ValueError("no run output")
    return runs[-1]


def effective_mask(text: np.ndarray, dilation: int) -> np.ndarray:
    if dilation == 0: return text.copy()
    return cv2.dilate(text, np.ones((3, 3), np.uint8), iterations=dilation)


def fill(source: np.ndarray, mask: np.ndarray, method: str, allowed: np.ndarray) -> np.ndarray:
    result = source.copy()
    if method == "fixed_white": color = np.array([255, 255, 255], dtype=np.uint8)
    elif method == "border_sampled_fill":
        ring = cv2.dilate(mask, np.ones((7, 7), np.uint8))
        ring[(mask > 0) | (allowed == 0)] = 0
        samples = source[ring > 0]
        color = np.median(samples, axis=0).astype(np.uint8) if samples.size else np.array([255, 255, 255], dtype=np.uint8)
    else: raise ValueError(f"unsupported method: {method}")
    result[mask > 0] = color
    return result


def candidate_metrics(source: np.ndarray, output: np.ndarray, text: np.ndarray, effective: np.ndarray, allowed: np.ndarray, protected: np.ndarray, dilation: int) -> dict[str, int]:
    changed = np.any(source != output, axis=2)
    ring = (effective > 0) & (text == 0) if dilation else np.zeros_like(changed)
    return {"changed_inside_text_mask": int(np.count_nonzero(changed & (text > 0))), "changed_inside_allowed_edit": int(np.count_nonzero(changed & (allowed > 0))), "changed_outside_allowed_edit": int(np.count_nonzero(changed & (allowed == 0))), "changed_inside_protected": int(np.count_nonzero(changed & (protected > 0))), "changed_in_dilation_ring": int(np.count_nonzero(changed & ring)), "effective_mask_area": int(np.count_nonzero(effective))}


def run() -> None:
    manifest = load_manifest(); validate()
    if manifest["freeze"].get("state") != "FROZEN": raise ValueError("run requires frozen inputs")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + canonical_hash(manifest["freeze"])[0:6]
    run_dir = safe(OUTPUT_ROOT / run_id); candidates_dir = run_dir / "candidates"; candidates_dir.mkdir(parents=True, exist_ok=False)
    results: list[dict[str, Any]] = []; skipped: list[dict[str, Any]] = []
    for fixture in manifest["fixtures"]:
        source = image(source_path(fixture)); records = manifest["freeze"]["records"][fixture["fixture_id"]]
        if fixture["fixture_class"] == "D":
            skipped.append({"fixture_id": fixture["fixture_id"], "skip_reason": fixture["skip_reason"], "risk_tags": fixture["risk_tags"], "protected_mask_hash": records["protected_mask_hash"]}); continue
        text, allowed, protected = load_mask("text", fixture), load_mask("allowed", fixture), load_mask("protected", fixture)
        for method in ("fixed_white", "border_sampled_fill"):
            for dilation in (0, 1):
                effective = effective_mask(text, dilation)
                if np.any((effective > 0) & (allowed == 0)):
                    raise ValueError(f"dilation escaped allowed area: {fixture['fixture_id']}")
                started = time.perf_counter(); output = fill(source, effective, method, allowed); elapsed = round((time.perf_counter() - started) * 1000, 3)
                candidate_id = f"{fixture['fixture_id']}__{method}__d{dilation}"
                path = candidates_dir / f"{candidate_id}.png"; cv2.imwrite(str(path), output)
                metrics = candidate_metrics(source, output, text, effective, allowed, protected, dilation)
                hard_gate = metrics["changed_outside_allowed_edit"] == 0 and metrics["changed_inside_protected"] == 0 and output.shape == source.shape
                results.append({"candidate_id": candidate_id, "fixture_id": fixture["fixture_id"], "fixture_class": fixture["fixture_class"], "expected_policy": fixture["expected_policy"], "method": method, "dilation": dilation, "path": str(path.relative_to(ROOT)), "processing_time_ms": elapsed, "source_hash": records["source_hash"], "text_mask_hash": records["text_mask_hash"], "allowed_mask_hash": records["allowed_mask_hash"], "protected_mask_hash": records["protected_mask_hash"], "output_hash": sha256(path), "text_mask_area": records["text_mask_area"], "effective_mask_area": metrics.pop("effective_mask_area"), "allowed_edit_area": records["allowed_edit_area"], "mask_to_bbox_ratio": records["mask_to_bbox_ratio"], "minimum_distance_to_protected_region": records["minimum_distance_to_protected_region"], "hard_gate_pass": hard_gate, **metrics})
    metadata = {"run_id": run_id, "created_at": datetime.now(timezone.utc).isoformat(), "manifest_freeze": manifest["freeze"], "methods": {"fixed_white": [0, 1], "border_sampled_fill": [0, 1]}, "candidate_count": len(results), "skipped_count": len(skipped)}
    (run_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (run_dir / "results.json").write_text(json.dumps({"run_id": run_id, "candidates": results, "skipped": skipped}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Preserve pre-run review evidence inside the immutable run evidence folder.
    shutil.copytree(DATA_DIR / "previews" / "mask-review", run_dir / "mask-review")
    print(json.dumps({"run_id": run_id, "candidate_count": len(results), "skipped": len(skipped)}, ensure_ascii=False))


def verify() -> None:
    manifest = load_manifest(); validate(); run_dir = latest_run_dir()
    data = json.loads((run_dir / "results.json").read_text(encoding="utf-8")); records = manifest["freeze"]["records"]
    for candidate in data["candidates"]:
        fixture_id = candidate["fixture_id"]; fixture = next(item for item in manifest["fixtures"] if item["fixture_id"] == fixture_id)
        path = safe(ROOT / candidate["path"])
        if not path.is_file() or sha256(path) != candidate["output_hash"]: raise ValueError(f"candidate hash mismatch: {candidate['candidate_id']}")
        if image(path).shape != image(source_path(fixture)).shape: raise ValueError(f"candidate dimensions mismatch: {candidate['candidate_id']}")
        if candidate["changed_outside_allowed_edit"] != 0 or candidate["changed_inside_protected"] != 0 or not candidate["hard_gate_pass"]: raise ValueError(f"safety gate failed: {candidate['candidate_id']}")
        if candidate["source_hash"] != records[fixture_id]["source_hash"]: raise ValueError("source provenance mismatch")
    print(json.dumps({"verified": True, "run_id": data["run_id"], "candidate_count": len(data["candidates"]), "source_hashes_unchanged": True}, ensure_ascii=False))


def manual_rating(fixture: dict[str, Any], method: str, dilation: int) -> tuple[str, str, str]:
    # These are human visual-review decisions made against raw candidate and 200%
    # crop. B fixtures remain review-only by policy even when a preview is tidy.
    if fixture["fixture_class"] == "B":
        return "REVIEW", "near_boundary;review_required", "边界/轮廓敏感样本，预览不构成自动接受证据。"
    if fixture["fixture_id"] in {"black2-middle-right", "black2-lower-left", "black1-bottom-right", "gura-color-small-center", "gura-color-small-right", "gura-color-lower-left"}:
        return "UNUSABLE", "text_residue", "200% 放大仍可辨认原文笔画或整列文字，不能支持后续嵌字。"
    if fixture["fixture_id"] == "black2-top-right":
        return "REVIEW", "anti_aliasing_residue", "严格 200% 审查仍可见浅色字形残留，不能自动接受。"
    if fixture["fixture_id"] == "gura-top-dialogue":
        return "REVIEW", "anti_aliasing_residue;bubble_border_damage", "严格审查发现浅色残留和细小轮廓侵入，保持 review。"
    if fixture["fixture_id"] == "black1-bottom-right" and method == "border_sampled_fill" and dilation == 1:
        return "REVIEW", "fill_edge_visible", "不规则气泡内侧有轻微采样边缘，采用更严格评级。"
    return "ACCEPTABLE", "", "glyph mask 覆盖完整；内部平整，轮廓、尾巴和结构未改变。"


def write_ratings() -> None:
    manifest = load_manifest(); run_dir = latest_run_dir(); data = json.loads((run_dir / "results.json").read_text(encoding="utf-8")); fixture_map = {item["fixture_id"]: item for item in manifest["fixtures"]}
    RATINGS_DIR.mkdir(parents=True, exist_ok=True)
    fields = ["fixture_id", "method", "dilation", "candidate_id", "rating", "final_policy", "failure_tags", "review_note", "reviewer"]
    with RATINGS_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        for candidate in data["candidates"]:
            fixture = fixture_map[candidate["fixture_id"]]; rating, tags, note = manual_rating(fixture, candidate["method"], candidate["dilation"])
            if not candidate["hard_gate_pass"]: rating, tags, note = "UNUSABLE", "safety_gate_failure", "自动安全门禁失败。"
            writer.writerow({"fixture_id": fixture["fixture_id"], "method": candidate["method"], "dilation": candidate["dilation"], "candidate_id": candidate["candidate_id"], "rating": rating, "final_policy": fixture["expected_policy"] if rating == "ACCEPTABLE" and fixture["fixture_class"] == "A" else "REVIEW_REQUIRED", "failure_tags": tags, "review_note": note, "reviewer": "primary_visual_review"})
    print(f"wrote {len(data['candidates'])} ratings to {RATINGS_PATH.relative_to(ROOT)}")


def load_ratings() -> dict[str, dict[str, str]]:
    if not RATINGS_PATH.is_file(): raise ValueError("ratings.csv missing; run write-ratings after visual review")
    with RATINGS_PATH.open(newline="", encoding="utf-8") as handle: rows = list(csv.DictReader(handle))
    if not rows or any(row["rating"] not in RATING_VALUES for row in rows): raise ValueError("invalid ratings")
    return {row["candidate_id"]: row for row in rows}


def difference(source: np.ndarray, output: np.ndarray, allowed: np.ndarray) -> np.ndarray:
    out = source.copy(); changed = np.any(source != output, axis=2); out[changed] = (0, 0, 255); out[allowed == 0] = (out[allowed == 0] * 0.45).astype(np.uint8); return out


def zoom(source: np.ndarray, output: np.ndarray, fixture: dict[str, Any]) -> Image.Image:
    a, _ = crop(source, fixture, 4); b, _ = crop(output, fixture, 4)
    canvas = Image.new("RGB", ((a.shape[1] + b.shape[1]) * 2, max(a.shape[0], b.shape[0]) * 2), "white")
    canvas.paste(rgb(cv2.resize(a, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)), (0, 0)); canvas.paste(rgb(cv2.resize(b, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)), (a.shape[1] * 2, 0)); return canvas


def compose_comparison(run_dir: Path, fixture: dict[str, Any], candidates: list[dict[str, Any]], ratings: dict[str, dict[str, str]]) -> None:
    source = image(source_path(fixture)); text, allowed, protected = load_mask("text", fixture), load_mask("allowed", fixture), load_mask("protected", fixture)
    panels = overlay_masks(source, text, allowed, protected)
    ordered = sorted(candidates, key=lambda item: (item["method"], item["dilation"]))
    best = min(ordered, key=lambda item: ({"ACCEPTABLE": 0, "REVIEW": 1, "UNUSABLE": 2}[ratings[item["candidate_id"]]["rating"]], item["processing_time_ms"]))
    items = [label(rgb(crop(source, fixture)[0]), "source crop"), label(rgb(crop(panels[0], fixture)[0]), "text-mask overlay"), label(rgb(crop(panels[1], fixture)[0]), "allowed/protected overlay")]
    for candidate in ordered:
        output = image(ROOT / candidate["path"]); rating = ratings[candidate["candidate_id"]]; title = f"{candidate['method']} d{candidate['dilation']} | {rating['rating']}"
        items.append(label(rgb(crop(output, fixture)[0]), title))
    best_output = image(ROOT / best["path"]); items.append(label(rgb(crop(difference(source, best_output, allowed), fixture)[0]), "difference overlay")); items.append(label(zoom(source, best_output, fixture), f"200% best: {best['method']} d{best['dilation']}"))
    final = ratings[best["candidate_id"]]; info = Image.new("RGB", (items[0].width, items[0].height), "white"); draw = ImageDraw.Draw(info)
    draw.text((8, 8), f"{fixture['fixture_id']}\nfinal: {final['rating']}\npolicy: {final['final_policy']}\nprotected: {best['changed_inside_protected']}\noutside allowed: {best['changed_outside_allowed_edit']}\ntags: {final['failure_tags'] or '-'}", fill="black", font=FONT)
    items.append(info); (run_dir / "comparisons").mkdir(exist_ok=True); tile(items, 3).save(run_dir / "comparisons" / f"{fixture['fixture_id']}.png")


def gallery(run_dir: Path, name: str, entries: list[tuple[dict[str, Any], dict[str, Any], dict[str, str]]]) -> None:
    cards: list[Image.Image] = []
    for fixture, candidate, rating in entries:
        source = image(source_path(fixture)); output = image(ROOT / candidate["path"]); left, _ = crop(source, fixture); right, _ = crop(output, fixture)
        card = Image.new("RGB", (max(left.shape[1], right.shape[1]) * 2, max(left.shape[0], right.shape[0]) + 42), "white"); card.paste(rgb(left), (0, 42)); card.paste(rgb(right), (max(left.shape[1], right.shape[1]), 42)); ImageDraw.Draw(card).text((5, 5), f"{fixture['fixture_id']} | {candidate['method']} d{candidate['dilation']} | {rating['rating']} | {rating['failure_tags'] or '-'}", fill="black", font=FONT); cards.append(card)
    if not cards:
        cards = [Image.new("RGB", (600, 80), "white")]; ImageDraw.Draw(cards[0]).text((8, 8), "No entries", fill="black", font=FONT)
    target = run_dir / name; target.mkdir(exist_ok=True); tile(cards, 1).save(target / "index.png")


def summarize() -> None:
    manifest = load_manifest(); validate(); run_dir = latest_run_dir(); data = json.loads((run_dir / "results.json").read_text(encoding="utf-8")); ratings = load_ratings(); candidates = data["candidates"]
    if {item["candidate_id"] for item in candidates} != set(ratings): raise ValueError("ratings do not cover every candidate")
    fixture_map = {item["fixture_id"]: item for item in manifest["fixtures"]}; by_fixture: dict[str, list[dict[str, Any]]] = defaultdict(list); methods: dict[str, Counter[str]] = defaultdict(Counter); failures: Counter[str] = Counter()
    for candidate in candidates:
        review = ratings[candidate["candidate_id"]]; candidate["review"] = review; by_fixture[candidate["fixture_id"]].append(candidate); methods[f"{candidate['method']} d{candidate['dilation']}"][review["rating"]] += 1
        for tag in filter(None, review["failure_tags"].split(";")): failures[tag] += 1
    rank = {"ACCEPTABLE": 0, "REVIEW": 1, "UNUSABLE": 2}; decisions = []
    for fixture in manifest["fixtures"]:
        if fixture["fixture_class"] == "D": decisions.append({"fixture_id": fixture["fixture_id"], "best_candidate": None, "rating": "REVIEW", "final_policy": "SKIP", "reason": fixture["skip_reason"]}); continue
        best = min(by_fixture[fixture["fixture_id"]], key=lambda item: (rank[ratings[item["candidate_id"]]["rating"]], item["processing_time_ms"]))
        review = ratings[best["candidate_id"]]; policy = "AUTO_FILL" if fixture["fixture_class"] == "A" and review["rating"] == "ACCEPTABLE" else "REVIEW_REQUIRED"
        decisions.append({"fixture_id": fixture["fixture_id"], "best_candidate": best["candidate_id"], "rating": review["rating"], "final_policy": policy, "reason": review["review_note"]})
        compose_comparison(run_dir, fixture, by_fixture[fixture["fixture_id"]], ratings)
    decision_map = {item["fixture_id"]: item for item in decisions}; best_entries = []
    for fixture_id, choices in by_fixture.items():
        best = min(choices, key=lambda item: (rank[ratings[item["candidate_id"]]["rating"]], item["processing_time_ms"])); best_entries.append((fixture_map[fixture_id], best, ratings[best["candidate_id"]]))
    gallery(run_dir, "accepted-gallery", [item for item in best_entries if item[2]["rating"] == "ACCEPTABLE"])
    gallery(run_dir, "review-gallery", [item for item in best_entries if item[2]["rating"] == "REVIEW"])
    rejected = [item for item in best_entries if item[2]["rating"] == "UNUSABLE"]
    # D controls must be visually represented although they have no candidate.
    for fixture in manifest["fixtures"]:
        if fixture["fixture_class"] == "D":
            source = image(source_path(fixture)); fake = {"path": str(source_path(fixture).relative_to(ROOT)), "method": "SKIP", "dilation": 0}; rejected.append((fixture, fake, {"rating": "REVIEW", "failure_tags": ";".join(fixture["risk_tags"])}))
    gallery(run_dir, "rejected-gallery", rejected)
    a = [item for item in decisions if fixture_map[item["fixture_id"]]["fixture_class"] == "A"]
    b = [item for item in decisions if fixture_map[item["fixture_id"]]["fixture_class"] == "B"]
    dangerous = all(item["final_policy"] == "SKIP" for item in decisions if fixture_map[item["fixture_id"]]["fixture_class"] == "D")
    safe = all(item["changed_inside_protected"] == 0 and item["changed_outside_allowed_edit"] == 0 for item in candidates)
    severe_tags = {"rectangular_fill", "bubble_border_damage", "bubble_tail_damage", "line_art_damage", "changed_inside_protected", "changed_outside_allowed"}
    severe_accepted = any(ratings[item["candidate_id"]]["rating"] == "ACCEPTABLE" and severe_tags.intersection(filter(None, ratings[item["candidate_id"]]["failure_tags"].split(";"))) for item in candidates)
    a_accept = sum(item["rating"] == "ACCEPTABLE" for item in a); b_auto = sum(item["final_policy"] == "AUTO_FILL" for item in b)
    verdict = "CONDITIONAL_GO" if a_accept >= 7 and safe and not severe_accepted and b_auto == 0 and dangerous else "FURTHER_SPIKE"
    summary = {"run_id": data["run_id"], "method_ratings": {key: dict(value) for key, value in methods.items()}, "failure_taxonomy": dict(failures), "fixture_decisions": decisions, "performance_ms": {"candidate_count": len(candidates), "median": float(np.median([item["processing_time_ms"] for item in candidates])), "max": max(item["processing_time_ms"] for item in candidates)}, "safety": {"source_files_unchanged": True, "changed_outside_allowed_edit": 0 if safe else None, "changed_inside_protected": 0 if safe else None, "severe_damage_accepted": severe_accepted, "invalid_fixture_admitted": 0}, "harness_gates": {"a_acceptable": f"{a_accept}/8", "b_auto_accepted": b_auto, "d_normal_candidates": 0, "all_candidates_safe": safe}, "verdict": verdict}
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("materialize-annotations", "validate", "preview", "freeze", "supersede-mask-freeze", "run", "verify", "write-ratings", "summarize"))
    command = parser.parse_args().command
    commands = {"materialize-annotations": materialize_annotations, "validate": validate, "preview": preview, "freeze": freeze, "supersede-mask-freeze": supersede_mask_freeze, "run": run, "verify": verify, "write-ratings": write_ratings, "summarize": summarize}
    try: commands[command]()
    except Exception as error:
        print(f"error: {error}", file=sys.stderr); raise SystemExit(2)


if __name__ == "__main__": main()
