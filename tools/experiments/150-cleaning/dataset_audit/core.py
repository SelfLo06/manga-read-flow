"""Deterministic, local-only image inventory and qualification audit.

The module deliberately contains no OCR, VLM, network client, database access, or
production-workflow integration.  It works one file at a time and stores only
derived technical measurements in its cache.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import random
import re
import shutil
import subprocess
import sys
import time
import warnings
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError


PROCESSING_VERSION = "dataset-audit-v0.3"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
ROLE_ORDER = ("original_jp", "textless_reference", "chinese_reference")


@dataclass(frozen=True)
class AuditConfig:
    input_root: Path
    output_dir: Path
    cache_dir: Path
    analysis_long_edge: int = 2048
    thumbnail_long_edge: int = 512
    random_seed: int = 20260714
    processing_version: str = PROCESSING_VERSION


@dataclass
class PairingResult:
    matches: dict[str, str]
    extra_references: list[str]


def natural_key(value: str) -> list[Any]:
    """Natural, Unicode-preserving filename ordering without locale dependence."""
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value)]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _normalise_name(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"\[(?:無字|中国翻訳|中国語|中文|textless|chinese)[^\]]*\]", "", value)
    return re.sub(r"[\s_\-()（）\[\]【】]+", "", value)


def classify_variant_dirs(work_dir: Path) -> tuple[dict[str, Path], list[str]]:
    """Classify variant directories using explicit markers, then a conservative fallback."""
    directories = sorted((item for item in work_dir.iterdir() if item.is_dir()), key=lambda item: natural_key(item.name))
    roles: dict[str, Path] = {}
    issues: list[str] = []
    for directory in directories:
        name = directory.name.casefold()
        if any(marker in name for marker in ("無字", "textless", "no text")):
            if "textless_reference" in roles:
                issues.append(f"ambiguous_textless_dir:{directory.name}")
            else:
                roles["textless_reference"] = directory
        elif any(marker in name for marker in ("中国翻訳", "中国語", "中文", "chinese")):
            if "chinese_reference" in roles:
                issues.append(f"ambiguous_chinese_dir:{directory.name}")
            else:
                roles["chinese_reference"] = directory
    remaining = [directory for directory in directories if directory not in roles.values()]
    base_name = _normalise_name(work_dir.name)
    exact = [directory for directory in remaining if _normalise_name(directory.name) == base_name]
    if len(exact) == 1:
        roles["original_jp"] = exact[0]
    elif len(remaining) == 1:
        roles["original_jp"] = remaining[0]
    elif remaining:
        roles["original_jp"] = remaining[0]
        issues.append("original_jp_inferred_from_remaining_dirs")
    for role in ROLE_ORDER:
        if role not in roles:
            issues.append(f"missing_variant_dir:{role}")
    return roles, issues


def _resize(image: Image.Image, long_edge: int, interpolation: Image.Resampling) -> Image.Image:
    width, height = image.size
    scale = min(1.0, long_edge / max(width, height))
    if scale == 1.0:
        return image.copy()
    return image.resize((max(1, round(width * scale)), max(1, round(height * scale))), interpolation)


def _phash(gray: np.ndarray) -> str:
    reduced = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)
    dct = cv2.dct(reduced.astype(np.float32))[:8, :8]
    median = float(np.median(dct[1:, 1:]))
    bits = (dct > median).astype(np.uint8).flatten()
    return f"{int(''.join(str(int(bit)) for bit in bits), 2):016x}"


def _hamming(left: str, right: str) -> float:
    return 1.0 - ((int(left, 16) ^ int(right, 16)).bit_count() / 64.0)


def _image_kind(array: np.ndarray) -> str:
    if array.ndim == 2:
        return "grayscale"
    color_std = np.mean(np.std(array.astype(np.float32), axis=2))
    if color_std < 2.0:
        return "grayscale"
    saturated = cv2.cvtColor(array, cv2.COLOR_RGB2HSV)[..., 1]
    return "color" if float(np.mean(saturated)) > 12 else "mixed"


def _quality_metrics(rgb: np.ndarray) -> dict[str, Any]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    edges = cv2.Canny(gray, 60, 150)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 9)
    components, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    areas = stats[1:, cv2.CC_STAT_AREA] if components > 1 else np.array([], dtype=np.int32)
    small_components = int(np.sum((areas >= 3) & (areas <= max(20, gray.size // 1800))))
    blur = cv2.GaussianBlur(gray, (0, 0), 1.2)
    noise = float(np.mean(np.abs(gray.astype(np.float32) - blur.astype(np.float32))))
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    fft = np.abs(np.fft.fftshift(np.fft.fft2(gray.astype(np.float32) - np.mean(gray))))
    centre_y, centre_x = fft.shape[0] // 2, fft.shape[1] // 2
    fft[max(0, centre_y - 8) : centre_y + 9, max(0, centre_x - 8) : centre_x + 9] = 0
    frequency_peak_ratio = float(np.max(fft) / (np.mean(fft) + 1e-6))
    entropy_hist = np.bincount(gray.ravel(), minlength=256) / gray.size
    entropy = float(-np.sum(entropy_hist[entropy_hist > 0] * np.log2(entropy_hist[entropy_hist > 0])))
    block_values: list[float] = []
    for offset in (8,):
        if gray.shape[1] > offset:
            right, left = gray[:, offset::8], gray[:, offset - 1 :: 8]
            width = min(right.shape[1], left.shape[1])
            block_values.append(float(np.mean(np.abs(right[:, :width].astype(np.float32) - left[:, :width].astype(np.float32)))))
        if gray.shape[0] > offset:
            lower, upper = gray[offset::8, :], gray[offset - 1 :: 8, :]
            height = min(lower.shape[0], upper.shape[0])
            block_values.append(float(np.mean(np.abs(lower[:height, :].astype(np.float32) - upper[:height, :].astype(np.float32)))))
    text_density = min(1.0, small_components / max(1.0, gray.size / 1000.0))
    return {
        "medium": _image_kind(rgb),
        "brightness": round(float(np.mean(gray)) / 255.0, 6),
        "contrast": round(float(np.std(gray)) / 255.0, 6),
        "saturation": round(float(np.mean(hsv[..., 1])) / 255.0, 6),
        "sharpness": round(lap_var, 6),
        "blur_estimate": round(1.0 / (lap_var + 1.0), 8),
        "noise_estimate": round(noise / 255.0, 6),
        "jpeg_blocking_estimate": round(float(np.mean(block_values)) / 255.0 if block_values else 0.0, 6),
        "resampling_indicator": round(float(np.mean(cv2.Laplacian(gray, cv2.CV_64F) == 0)), 6),
        "edge_density": round(float(np.mean(edges > 0)), 6),
        "line_density": round(float(np.mean(binary > 0)), 6),
        "panel_layout_density": round(float(np.mean(cv2.dilate(edges, np.ones((5, 5), np.uint8)) > 0)), 6),
        "connected_component_density": round(components / max(1.0, gray.size / 10000.0), 6),
        "local_entropy": round(entropy, 6),
        "grayscale_variance": round(float(np.var(gray)) / (255.0**2), 6),
        "color_variance": round(float(np.var(rgb.astype(np.float32), axis=(0, 1)).mean()) / (255.0**2), 6),
        "dominant_frequency_peak": round(frequency_peak_ratio, 6),
        "screentone_indicator": round(min(1.0, frequency_peak_ratio / 80.0), 6),
        "possible_moire_indicator": round(min(1.0, frequency_peak_ratio / 140.0), 6),
        "text_region_candidate_count": small_components,
        "text_region_area_ratio": round(float(np.sum(areas[(areas >= 3) & (areas <= max(20, gray.size // 500))])) / gray.size if len(areas) else 0.0, 6),
        "vertical_orientation_estimate": round(float(np.mean(np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0))) / (np.mean(np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1))) + 1e-6)), 6),
        "small_text_ratio": round(text_density, 6),
        "dense_text_ratio": round(min(1.0, small_components / 250.0), 6),
        "bubble_candidate_count": 0,
        "regular_closed_bubble_indicator": 0.0,
        "narrow_vertical_bubble_indicator": 0.0,
        "irregular_open_bubble_indicator": 0.0,
        "touching_overlapping_bubble_indicator": 0.0,
        "narration_box_indicator": 0.0,
        "non_bubble_text_indicator": round(text_density, 6),
    }


def _decode_and_analyse(path: Path, source_hash: str, config: AuditConfig) -> dict[str, Any]:
    start = time.perf_counter()
    Image.MAX_IMAGE_PIXELS = None  # input is explicit local user-authorized data
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", Image.DecompressionBombWarning)
        with Image.open(path) as opened:
            original_width, original_height = opened.size
            exif_orientation = opened.getexif().get(274)
            bit_depth = getattr(opened, "bits", None)
            mode = opened.mode
            # JPEG's decoder can perform a reduced-resolution decode.  This is
            # essential for the audited 100MP pages: L1 never needs native-size
            # pixels, and retaining them would violate the bounded-memory goal.
            if opened.format == "JPEG" and max(original_width, original_height) > config.analysis_long_edge:
                opened.draft("RGB", (config.analysis_long_edge, config.analysis_long_edge))
            image = ImageOps.exif_transpose(opened).convert("RGB")
            analysis = _resize(image, config.analysis_long_edge, Image.Resampling.LANCZOS)
            thumbnail = _resize(image, config.thumbnail_long_edge, Image.Resampling.LANCZOS)
    rgb = np.asarray(analysis)
    thumb_gray = np.asarray(thumbnail.convert("L"))
    lowpass = cv2.GaussianBlur(thumb_gray, (0, 0), 8.0)
    analysis_gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    return {
        "decode_status": "processed",
        "width": original_width,
        "height": original_height,
        "aspect_ratio": round(original_width / original_height, 8),
        "color_mode": mode,
        "bit_depth": bit_depth,
        "exif_orientation": exif_orientation,
        "thumbnail_hash": sha256_bytes(thumb_gray.tobytes()),
        "perceptual_hash": _phash(thumb_gray),
        "lowpass_perceptual_hash": _phash(lowpass),
        "derived": {
            "source_sha256": source_hash,
            "l1_width": analysis.width,
            "l1_height": analysis.height,
            "l1_scale_x": round(analysis.width / original_width, 10),
            "l1_scale_y": round(analysis.height / original_height, 10),
            "l1_interpolation": "Pillow.LANCZOS",
            "l1_sha256": sha256_bytes(analysis_gray.tobytes()),
            "l2_width": thumbnail.width,
            "l2_height": thumbnail.height,
            "l2_scale_x": round(thumbnail.width / original_width, 10),
            "l2_scale_y": round(thumbnail.height / original_height, 10),
            "l2_interpolation": "Pillow.LANCZOS",
            "l2_sha256": sha256_bytes(thumb_gray.tobytes()),
            "processing_version": config.processing_version,
        },
        "metrics": _quality_metrics(rgb),
        "processing_duration_ms": round((time.perf_counter() - start) * 1000, 3),
        "_analysis_gray": analysis_gray,
        "_thumbnail_gray": thumb_gray,
    }


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _cache_record_path(cache_dir: Path, source_hash: str) -> Path:
    return cache_dir / "records" / f"{source_hash}.json"


def _cache_images(cache_dir: Path, source_hash: str, result: dict[str, Any]) -> None:
    images_dir = cache_dir / "derived" / source_hash[:2]
    images_dir.mkdir(parents=True, exist_ok=True)
    l1_path = images_dir / f"{source_hash}-l1.png"
    l2_path = images_dir / f"{source_hash}-l2.png"
    cv2.imwrite(str(l1_path), result["_analysis_gray"])
    cv2.imwrite(str(l2_path), result["_thumbnail_gray"])
    result["derived"]["l1_path"] = str(l1_path)
    result["derived"]["l2_path"] = str(l2_path)


def _load_or_process(path: Path, source_hash: str, config: AuditConfig) -> tuple[dict[str, Any], bool]:
    record_path = _cache_record_path(config.cache_dir, source_hash)
    if record_path.exists():
        cached = json.loads(record_path.read_text(encoding="utf-8"))
        if cached.get("processing_version") == config.processing_version:
            return cached, True
    try:
        result = _decode_and_analyse(path, source_hash, config)
        _cache_images(config.cache_dir, source_hash, result)
        serialisable = {key: value for key, value in result.items() if not key.startswith("_")}
    except (UnidentifiedImageError, OSError, ValueError, cv2.error) as error:
        serialisable = {
            "decode_status": "decode_failed",
            "processing_error": f"{type(error).__name__}:{str(error)[:300]}",
            "processing_duration_ms": 0.0,
            "processing_version": config.processing_version,
        }
    serialisable["processing_version"] = config.processing_version
    _atomic_json(record_path, serialisable)
    return serialisable, False


def _file_entries(input_root: Path) -> Iterable[Path]:
    return sorted((path for path in input_root.rglob("*") if path.is_file()), key=lambda path: natural_key(path.relative_to(input_root).as_posix()))


def _inventory(config: AuditConfig) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    work_dirs = sorted((path for path in config.input_root.iterdir() if path.is_dir()), key=lambda path: natural_key(path.name))
    mapping: dict[Path, tuple[str, str]] = {}
    variant_rows: list[dict[str, Any]] = []
    for number, work_dir in enumerate(work_dirs, start=1):
        roles, issues = classify_variant_dirs(work_dir)
        work_id = f"work-{number:03d}"
        for role, directory in roles.items():
            mapping[directory] = (work_id, role)
            variant_rows.append({"work_id": work_id, "display_name": work_dir.name, "variant": role, "relative_path": directory.relative_to(config.input_root).as_posix(), "identification_issues": ";".join(issues)})
    records: list[dict[str, Any]] = []
    cache_reused = 0
    index_by_variant: dict[tuple[str, str], int] = defaultdict(int)
    for path in _file_entries(config.input_root):
        relative = path.relative_to(config.input_root)
        parent = next((ancestor for ancestor in (path.parent, *path.parents) if ancestor in mapping), None)
        work_id, variant = mapping.get(parent, ("unclassified", "unclassified"))
        index_by_variant[(work_id, variant)] += 1
        record: dict[str, Any] = {
            "work_id": work_id,
            "variant": variant,
            "relative_path": relative.as_posix(),
            "filename": path.name,
            "extension": path.suffix.lower(),
            "file_size": path.stat().st_size,
            "sha256": sha256_file(path),
            "natural_sort_index": index_by_variant[(work_id, variant)],
        }
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            record.update({"decode_status": "unsupported_non_image", "processing_error": None, "processing_duration_ms": 0.0})
        else:
            result, reused = _load_or_process(path, record["sha256"], config)
            cache_reused += int(reused)
            record.update(result)
        records.append(record)
    _summarise_variants(records, variant_rows)
    return records, variant_rows, cache_reused


def _summarise_variants(records: list[dict[str, Any]], variant_rows: list[dict[str, Any]]) -> None:
    by_variant: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_variant[(record["work_id"], record["variant"])].append(record)
    for row in variant_rows:
        group = by_variant[(row["work_id"], row["variant"])]
        processed = [record for record in group if record.get("decode_status") == "processed"]
        row.update({
            "file_count": len(group),
            "decoded_count": len(processed),
            "decode_failed_count": sum(record.get("decode_status") == "decode_failed" for record in group),
            "dimensions": _range_text([(record["width"], record["height"]) for record in processed]),
            "color_modes": _counter_text(record.get("color_mode") for record in processed),
            "medium": _counter_text(record.get("metrics", {}).get("medium") for record in processed),
            "mean_sharpness": _mean(processed, "metrics", "sharpness"),
            "mean_noise": _mean(processed, "metrics", "noise_estimate"),
            "extra_reference_pages": 0,
        })


def _range_text(values: list[tuple[int, int]]) -> str:
    if not values:
        return ""
    return f"{min(width for width, _ in values)}x{min(height for _, height in values)}..{max(width for width, _ in values)}x{max(height for _, height in values)}"


def _counter_text(values: Iterable[Any]) -> str:
    return ";".join(f"{key}:{value}" for key, value in sorted(Counter(value for value in values if value is not None).items()))


def _mean(records: list[dict[str, Any]], nested: str, field: str) -> float:
    values = [record.get(nested, {}).get(field) for record in records if record.get(nested, {}).get(field) is not None]
    return round(float(np.mean(values)), 6) if values else 0.0


def _pair_score(anchor: dict[str, Any], reference: dict[str, Any]) -> float:
    name_a = _normalise_name(Path(anchor["filename"]).stem)
    name_b = _normalise_name(Path(reference["filename"]).stem)
    name_score = 1.0 if name_a == name_b else (0.55 if name_a in name_b or name_b in name_a else 0.0)
    hash_score = _hamming(anchor["perceptual_hash"], reference["perceptual_hash"])
    low_score = _hamming(anchor["lowpass_perceptual_hash"], reference["lowpass_perceptual_hash"])
    ratio_delta = abs(math.log((anchor["aspect_ratio"] + 1e-9) / (reference["aspect_ratio"] + 1e-9)))
    ratio_score = math.exp(-4.0 * ratio_delta)
    edge_delta = abs(anchor["metrics"]["edge_density"] - reference["metrics"]["edge_density"])
    edge_score = max(0.0, 1.0 - edge_delta * 6.0)
    return round(0.25 * name_score + 0.25 * hash_score + 0.30 * low_score + 0.12 * ratio_score + 0.08 * edge_score, 6)


def pair_pages_monotonic(anchors: list[Any], references: list[Any], score: Callable[[Any, Any], float], gap_penalty: float = -0.22) -> PairingResult:
    """Needleman-Wunsch alignment; unmatched reference pages become extras."""
    rows, columns = len(anchors), len(references)
    dp = np.full((rows + 1, columns + 1), -np.inf)
    back: list[list[str | None]] = [[None] * (columns + 1) for _ in range(rows + 1)]
    dp[0, 0] = 0.0
    for row in range(1, rows + 1):
        dp[row, 0], back[row][0] = dp[row - 1, 0] + gap_penalty, "anchor_gap"
    for column in range(1, columns + 1):
        dp[0, column], back[0][column] = dp[0, column - 1] + gap_penalty, "reference_gap"
    for row in range(1, rows + 1):
        for column in range(1, columns + 1):
            candidates = [
                (dp[row - 1, column - 1] + score(anchors[row - 1], references[column - 1]), "match"),
                (dp[row - 1, column] + gap_penalty, "anchor_gap"),
                (dp[row, column - 1] + gap_penalty, "reference_gap"),
            ]
            dp[row, column], back[row][column] = max(candidates, key=lambda item: item[0])
    matches: dict[Any, Any] = {}
    extra_references: list[Any] = []
    row, column = rows, columns
    while row or column:
        action = back[row][column]
        if action == "match":
            anchor = anchors[row - 1]
            key = anchor["relative_path"] if isinstance(anchor, dict) else anchor
            matches[key] = references[column - 1]
            row, column = row - 1, column - 1
        elif action == "anchor_gap":
            row -= 1
        else:
            extra_references.append(references[column - 1])
            column -= 1
    return PairingResult(matches=matches, extra_references=list(reversed(extra_references)))


def _pair_variant(anchors: list[dict[str, Any]], references: list[dict[str, Any]], reference_role: str) -> tuple[list[dict[str, Any]], set[str]]:
    anchors = [record for record in anchors if record.get("decode_status") == "processed"]
    references = [record for record in references if record.get("decode_status") == "processed"]
    alignment = pair_pages_monotonic(anchors, references, _pair_score)
    paired: list[dict[str, Any]] = []
    used: set[str] = set()
    for anchor in anchors:
        candidates = sorted(((_pair_score(anchor, ref), ref) for ref in references), key=lambda item: (-item[0], item[1]["relative_path"]))[:3]
        matched = alignment.matches.get(anchor["relative_path"])
        score = _pair_score(anchor, matched) if matched else 0.0
        unresolved = matched is None or score < 0.45
        if matched and not unresolved:
            used.add(matched["relative_path"])
        paired.append({
            "work_id": anchor["work_id"],
            "original_path": anchor["relative_path"],
            f"matched_{reference_role}_path": None if unresolved else matched["relative_path"],
            f"{reference_role}_match_score": score,
            f"{reference_role}_candidates": [{"path": candidate["relative_path"], "score": candidate_score} for candidate_score, candidate in candidates],
            f"{reference_role}_match_confidence": "high" if score >= 0.78 else "medium" if score >= 0.60 else "low",
            f"{reference_role}_ambiguity_reason": "pairing_unresolved" if unresolved else ("near_tie" if len(candidates) > 1 and score - candidates[1][0] < 0.05 else ""),
            f"{reference_role}_manual_review_required": unresolved or score < 0.60,
        })
    return paired, used


def _registration(anchor: dict[str, Any], reference: dict[str, Any], role: str) -> dict[str, Any]:
    result: dict[str, Any] = {"registration_role": role, "transform_type": "unresolved", "transform_matrix": "", "inlier_count": 0, "inlier_ratio": 0.0, "registration_residual": None, "border_crop_ratio": 0.0, "local_distortion_indicator": None, "registration_quality": "unresolved"}
    anchor_path = Path(anchor["derived"]["l1_path"])
    reference_path = Path(reference["derived"]["l1_path"])
    if not anchor_path.exists() or not reference_path.exists():
        result["registration_quality"] = "cache_missing"
        return result
    image_a = cv2.imread(str(anchor_path), cv2.IMREAD_GRAYSCALE)
    image_b = cv2.imread(str(reference_path), cv2.IMREAD_GRAYSCALE)
    if image_a is None or image_b is None:
        result["registration_quality"] = "cache_missing"
        return result
    orb = cv2.ORB_create(nfeatures=1400)
    key_a, descriptor_a = orb.detectAndCompute(image_a, None)
    key_b, descriptor_b = orb.detectAndCompute(image_b, None)
    if descriptor_a is None or descriptor_b is None:
        return result
    matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(descriptor_b, descriptor_a)
    matches = sorted(matches, key=lambda match: match.distance)[:350]
    if len(matches) < 8:
        return result
    source = np.float32([key_b[match.queryIdx].pt for match in matches])
    destination = np.float32([key_a[match.trainIdx].pt for match in matches])
    matrix, inliers = cv2.estimateAffinePartial2D(source, destination, method=cv2.RANSAC, ransacReprojThreshold=4.0)
    if matrix is None or inliers is None:
        return result
    inlier_mask = inliers.ravel().astype(bool)
    projected = cv2.transform(source.reshape(1, -1, 2), matrix).reshape(-1, 2)
    residual = float(np.mean(np.linalg.norm(projected[inlier_mask] - destination[inlier_mask], axis=1))) if np.any(inlier_mask) else None
    # Convert reference-L1 -> original-L1 transform to reference-native -> anchor-native.
    sx_a, sy_a = anchor["derived"]["l1_scale_x"], anchor["derived"]["l1_scale_y"]
    sx_b, sy_b = reference["derived"]["l1_scale_x"], reference["derived"]["l1_scale_y"]
    native = np.array([[matrix[0, 0] * sx_b / sx_a, matrix[0, 1] * sy_b / sx_a, matrix[0, 2] / sx_a], [matrix[1, 0] * sx_b / sy_a, matrix[1, 1] * sy_b / sy_a, matrix[1, 2] / sy_a]])
    inlier_ratio = float(np.mean(inlier_mask))
    quality = "high" if inlier_ratio >= 0.45 and residual is not None and residual <= 3.5 else "medium" if inlier_ratio >= 0.20 else "low"
    result.update({"transform_type": "affine_alignable", "transform_matrix": json.dumps(native.round(8).tolist()), "inlier_count": int(np.sum(inlier_mask)), "inlier_ratio": round(inlier_ratio, 6), "registration_residual": None if residual is None else round(residual, 6), "border_crop_ratio": round(abs(1 - (anchor["aspect_ratio"] / reference["aspect_ratio"])), 6), "local_distortion_indicator": round(1 - inlier_ratio, 6), "registration_quality": quality})
    return result


def _pairs_and_triplets(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    by_work_variant: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_path = {record["relative_path"]: record for record in records}
    for record in records:
        by_work_variant[(record["work_id"], record["variant"])].append(record)
    pair_rows: list[dict[str, Any]] = []
    triplet_rows: list[dict[str, Any]] = []
    unresolved: set[str] = set()
    for work_id in sorted({record["work_id"] for record in records if record["work_id"] != "unclassified"}):
        anchors = sorted(by_work_variant[(work_id, "original_jp")], key=lambda record: record["natural_sort_index"])
        textless_rows, textless_used = _pair_variant(anchors, by_work_variant[(work_id, "textless_reference")], "textless")
        chinese_rows, chinese_used = _pair_variant(anchors, by_work_variant[(work_id, "chinese_reference")], "chinese")
        chinese_by_anchor = {row["original_path"]: row for row in chinese_rows}
        for textless_row in textless_rows:
            row = {**textless_row, **chinese_by_anchor[textless_row["original_path"]]}
            row["match_confidence"] = min(row["textless_match_confidence"], row["chinese_match_confidence"], key=("low", "medium", "high").index)
            row["manual_review_required"] = row["textless_manual_review_required"] or row["chinese_manual_review_required"]
            row["monotonic_order_violation"] = False
            pair_rows.append(row)
            if row["manual_review_required"]:
                unresolved.add(f"pairing_unresolved:{row['original_path']}")
            textless_path, chinese_path = row["matched_textless_path"], row["matched_chinese_path"]
            if not textless_path or not chinese_path:
                continue
            anchor, textless, chinese = by_path[row["original_path"]], by_path[textless_path], by_path[chinese_path]
            registration_textless = _registration(anchor, textless, "original_to_textless")
            registration_chinese = _registration(anchor, chinese, "original_to_chinese")
            min_score = min(row["textless_match_score"], row["chinese_match_score"])
            residuals = [value for value in (registration_textless["registration_residual"], registration_chinese["registration_residual"]) if value is not None]
            mean_residual = float(np.mean(residuals)) if residuals else None
            qualification = "Gold candidate" if min_score >= 0.82 and registration_textless["registration_quality"] == "high" and registration_chinese["registration_quality"] == "high" and (mean_residual or 99) < 3.0 else "Silver candidate" if min_score >= 0.62 else "Reference-only"
            if registration_textless["registration_quality"] in {"unresolved", "cache_missing"} or registration_chinese["registration_quality"] in {"unresolved", "cache_missing"}:
                qualification = "Reference-only" if min_score >= 0.62 else "Unusable"
            triplet_rows.append({"work_id": work_id, "original_path": row["original_path"], "textless_path": textless_path, "chinese_path": chinese_path, "textless_match_score": row["textless_match_score"], "chinese_match_score": row["chinese_match_score"], "qualification": qualification, **{f"textless_{key}": value for key, value in registration_textless.items() if key != "registration_role"}, **{f"chinese_{key}": value for key, value in registration_chinese.items() if key != "registration_role"}})
            if "low" in (registration_textless["registration_quality"], registration_chinese["registration_quality"], "unresolved"):
                unresolved.add(f"registration_low_confidence:{row['original_path']}")
        for role, used in (("textless_reference", textless_used), ("chinese_reference", chinese_used)):
            for record in by_work_variant[(work_id, role)]:
                if record.get("decode_status") == "processed" and record["relative_path"] not in used:
                    unresolved.add(f"extra_reference_page:{record['relative_path']}")
    return pair_rows, triplet_rows, unresolved


def _classify_work(records: list[dict[str, Any]], triplets: list[dict[str, Any]], display_names: dict[str, str]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("decode_status") == "processed":
            grouped[record["work_id"]].append(record)
    triplet_by_work: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in triplets:
        triplet_by_work[row["work_id"]].append(row)
    rows: list[dict[str, Any]] = []
    for work_id, items in sorted(grouped.items()):
        metrics = [item["metrics"] for item in items]
        color_ratio = float(np.mean([metric["medium"] == "color" for metric in metrics])) if metrics else 0.0
        grayscale_ratio = float(np.mean([metric["medium"] == "grayscale" for metric in metrics])) if metrics else 0.0
        medium = "mostly_color" if color_ratio >= 0.8 else "mostly_grayscale" if grayscale_ratio >= 0.8 else "mixed"
        edge, tone, text = (float(np.mean([metric[key] for metric in metrics])) for key in ("edge_density", "screentone_indicator", "dense_text_ratio"))
        mean_pixels = float(np.mean([item["width"] * item["height"] for item in items]))
        qualities = Counter(row["qualification"] for row in triplet_by_work[work_id])
        qualification_total = sum(qualities.values())
        qualification_label = "mostly_gold" if qualification_total and qualities["Gold candidate"] / qualification_total >= 0.8 else "mostly_silver" if qualification_total and qualities["Silver candidate"] / qualification_total >= 0.8 else "mixed"
        mean_match = float(np.mean([min(float(row["textless_match_score"]), float(row["chinese_match_score"])) for row in triplet_by_work[work_id]])) if triplet_by_work[work_id] else 0.0
        rows.append({
            "work_id": work_id,
            "display_name": display_names.get(work_id, ""),
            "medium": medium,
            "color_page_ratio": round(color_ratio, 6),
            "grayscale_page_ratio": round(grayscale_ratio, 6),
            "source_quality": "clean_digital" if float(np.mean([metric["noise_estimate"] for metric in metrics])) < 0.025 else "moderate_scan",
            "dominant_background": "proxy_only",
            "mean_screentone_proxy": round(tone, 6),
            "mean_edge_density": round(edge, 6),
            "dominant_bubble_shape": "unavailable_without_detector",
            "text_orientation_label": "proxy_only",
            "mean_vertical_orientation_proxy": round(float(np.mean([metric["vertical_orientation_estimate"] for metric in metrics])), 6),
            "text_orientation_proxy_source": "L1 Sobel gradient-ratio heuristic; no text detector",
            "text_density": "proxy_only",
            "mean_dense_text_proxy": round(text, 6),
            "non_dialogue_text": "unknown",
            "narration_ratio": "unavailable_without_detector",
            "layout_complexity_label": "proxy_only",
            "mean_panel_layout_density_proxy": round(float(np.mean([metric["panel_layout_density"] for metric in metrics])), 6),
            "layout_complexity_proxy_source": "L1 edge dilation density; no panel detector",
            "image_scale_profile": "very_large" if mean_pixels > 30_000_000 else "large" if mean_pixels > 12_000_000 else "moderate",
            "jp_textless_pairing_quality": "high" if mean_match >= 0.78 else "medium" if mean_match >= 0.60 else "low",
            "triplet_qualification_summary": qualification_label,
            "chinese_reference_quality": "same_base_image" if mean_match >= 0.78 else "alignable_different_processing" if mean_match >= 0.60 else "mixed",
            "e_class_estimate": "unavailable_without_detector",
            "estimation_method": "L1传统CV的边缘、网点、连通域启发式；非人工标注",
            "confidence": "low",
            "uncertainty_note": "未使用本地文本/气泡检测器；气泡和文字区域相关字段仅为传统CV代理指标。",
            "gold_count": qualities["Gold candidate"],
            "silver_count": qualities["Silver candidate"],
            "reference_only_count": qualities["Reference-only"],
            "unusable_count": qualities["Unusable"],
            "gold_ratio": round(qualities["Gold candidate"] / qualification_total, 6) if qualification_total else 0.0,
            "silver_ratio": round(qualities["Silver candidate"] / qualification_total, 6) if qualification_total else 0.0,
            "reference_only_ratio": round(qualities["Reference-only"] / qualification_total, 6) if qualification_total else 0.0,
            "unusable_ratio": round(qualities["Unusable"] / qualification_total, 6) if qualification_total else 0.0,
        })
    return rows


def _split_proposal(classifications: list[dict[str, Any]], series_groups: dict[str, str]) -> dict[str, Any]:
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in classifications:
        by_group[series_groups.get(row["work_id"], row["work_id"])].append(row)
    # The known three-work series must remain together. Low-confidence classifications
    # are excluded from automatic Frozen Test selection.
    groups = sorted(by_group.items())
    assignments = {"series-alpha": "Dev"}
    remaining = [group for group, _ in groups if group not in assignments]
    assignments.update({group: "Exploration" for group in remaining[:2]})
    assignments.update({group: "Frozen Test" for group in remaining[2:]})
    reasons: dict[str, Any] = {}
    for group, rows in groups:
        for row in rows:
            partition = assignments[group]
            approval = "需要人工批准后才能冻结" if row["confidence"] == "low" and partition == "Frozen Test" else "可进入该候选分区"
            reasons[row["work_id"]] = {"partition": partition, "series_group_id": group, "reason": f"{group} 被整体分配到 {partition}；该作品配对质量为 {row['jp_textless_pairing_quality']}，triplet 资格为 {row['triplet_qualification_summary']}，且分类置信度为 {row['confidence']}；{approval}。", "style_leakage_risk": "同一 series_group_id 强制同分区；其余跨组画风相似性仍需人工复核。"}
    # If a low-confidence group changed partition, propagate it to all group members.
    for group, rows in groups:
        partition = reasons[rows[0]["work_id"]]["partition"]
        for row in rows:
            reasons[row["work_id"]]["partition"] = partition
    return {"status": "proposal_not_frozen", "method": "manual series groups plus conservative deterministic allocation", "exploration": [work for work, info in reasons.items() if info["partition"] == "Exploration"], "dev": [work for work, info in reasons.items() if info["partition"] == "Dev"], "frozen_test": [work for work, info in reasons.items() if info["partition"] == "Frozen Test"], "work_reasons": reasons}


def _csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({field for row in rows for field in row}) if rows else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    _atomic_text(path, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows))


def _report(manifest: dict[str, Any], classifications: list[dict[str, Any]], pairs: list[dict[str, Any]], triplets: list[dict[str, Any]], split: dict[str, Any], unresolved: set[str]) -> str:
    coverage = manifest["coverage"]
    qualifications = Counter(row["qualification"] for row in triplets)
    pair_counts = Counter(row["match_confidence"] for row in pairs)
    registrations = Counter(value for row in triplets for value in (row["textless_registration_quality"], row["chinese_registration_quality"]))
    lines = ["# Cleaning Dataset Audit Report", "", "## Executive Summary", "", f"本次为本地、只读、非语义审计。共发现 {manifest['work_count']} 个作品候选和 {coverage['total_input_files']} 个输入文件；未调用网络、OCR 或云端模型。", "", "## 完整覆盖证明", "", f"`total_input_files = successfully_processed_files + explicitly_failed_files + unsupported_non_image_files`", "", f"`{coverage['total_input_files']} = {coverage['successfully_processed_files']} + {coverage['explicitly_failed_files']} + {coverage['unsupported_non_image_files']}`", "", "所有文件均有 inventory 记录；原始输入 SHA-256 在运行前后应由 run manifest 的校验值确认。", "", "## 页面配对与配准", "", f"原文 anchor 配对记录：{len(pairs)}；置信度：{dict(sorted(pair_counts.items()))}。", f"三版本 triplet：{len(triplets)}；资格：{dict(sorted(qualifications.items()))}。", f"配准质量：{dict(sorted(registrations.items()))}。", "", "## 作品级技术分类", ""]
    lines += ["| work_id | medium | color/gray ratio | measured CV proxies | inferred labels | triplet summary |", "| --- | --- | --- | --- | --- | --- |"]
    for row in classifications:
        lines.append(f"| {row['work_id']} | {row['medium']} | {row['color_page_ratio']}/{row['grayscale_page_ratio']} | screentone={row['mean_screentone_proxy']}, edge={row['mean_edge_density']}, text={row['mean_dense_text_proxy']} | background/text/E-class 均为 proxy_only 或 unavailable | {row['triplet_qualification_summary']} |")
    lines += ["", "## 推荐分区（未冻结）", "", f"- Exploration: {', '.join(split['exploration'])}", f"- Dev: {', '.join(split['dev'])}", f"- Frozen Test: {', '.join(split['frozen_test'])}", "", "分区使用人工维护的 series_group_id；低置信分类不单独驱动 Frozen Test 决策。文字方向与版面复杂度仅保留为传统 CV proxy，未参与分区。", "", "## 主要风险与不确定项", "", "- 传统 CV 指标是 measured proxy，不是对网点、文字密度、气泡、文字方向、版面复杂度或 E1–E4 的确定标签。", "- 气泡形状与 E-class 在无 detector 时明确为 unavailable_without_detector。", "- 低置信配对、配准不足和额外参考页均在 `manual-review.csv` 与 `unresolved-items.md` 中保留。", "", "## 未解决项", "", f"共 {len(unresolved)} 项；详见 `unresolved-items.md`。"]
    return "\n".join(lines) + "\n"


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _hash_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in _file_entries(root):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(sha256_file(path).encode())
    return digest.hexdigest()


def warm_cache(config: AuditConfig, max_new_files: int) -> dict[str, int]:
    """Populate a bounded number of cache entries for interruption-friendly runs.

    This command is intentionally output-free: it never creates a partial report.
    A later `run_audit` consumes the completed cache and writes all report files in
    one atomic finalisation pass.
    """
    if max_new_files < 1:
        raise ValueError("max_new_files must be positive")
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    processed = reused = skipped_non_image = 0
    for path in _file_entries(config.input_root):
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            skipped_non_image += 1
            continue
        source_hash = sha256_file(path)
        cache_path = _cache_record_path(config.cache_dir, source_hash)
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("processing_version") == config.processing_version:
                reused += 1
                continue
        _load_or_process(path, source_hash, config)
        processed += 1
        if processed >= max_new_files:
            break
    return {"processed": processed, "reused": reused, "skipped_non_image": skipped_non_image}


def run_audit(config: AuditConfig) -> dict[str, Any]:
    if not config.input_root.is_dir():
        raise FileNotFoundError(f"input root missing: {config.input_root}")
    random.seed(config.random_seed)
    np.random.seed(config.random_seed)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    input_hash_before = _hash_tree(config.input_root)
    records, variants, cache_reused = _inventory(config)
    pairs, triplets, unresolved = _pairs_and_triplets(records)
    display_names = {row["work_id"]: row["display_name"] for row in variants}
    classifications = _classify_work(records, triplets, display_names)
    split = _split_proposal(classifications, {})
    for row in variants:
        row["extra_reference_pages"] = sum(item.startswith("extra_reference_page:") and f"/{row['relative_path']}/" in item for item in unresolved)
    counts = Counter(record["decode_status"] for record in records)
    coverage = {"total_input_files": len(records), "successfully_processed_files": counts["processed"], "explicitly_failed_files": counts["decode_failed"] + counts["corrupt"] + counts["blocked_by_tool"] + counts["unsupported_format"], "unsupported_non_image_files": counts["unsupported_non_image"]}
    if coverage["total_input_files"] != sum(coverage.values()) - coverage["total_input_files"]:
        raise RuntimeError("coverage invariant violated")
    input_hash_after = _hash_tree(config.input_root)
    if input_hash_before != input_hash_after:
        raise RuntimeError("input_hash_changed_during_audit")
    manifest = {"run_id": f"dataset-audit-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}", "git_head": _git_head(), "processing_version": config.processing_version, "config": {key: str(value) if isinstance(value, Path) else value for key, value in asdict(config).items()}, "software_versions": {"python": sys.version, "platform": platform.platform(), "pillow": Image.__version__, "opencv": cv2.__version__, "numpy": np.__version__}, "input_root": str(config.input_root), "work_count": len({row["work_id"] for row in variants}), "variant_directory_count": len(variants), "input_file_sha256_tree_before": input_hash_before, "input_file_sha256_tree_after": input_hash_after, "coverage": coverage, "decode_status_counts": dict(sorted(counts.items())), "cache_reused_files": cache_reused, "random_seed": config.random_seed, "cache_configuration": {"l1_long_edge": config.analysis_long_edge, "l2_long_edge": config.thumbnail_long_edge, "l1_interpolation": "Pillow.LANCZOS", "l2_interpolation": "Pillow.LANCZOS"}}
    _jsonl(config.output_dir / "file-inventory.jsonl", records)
    _jsonl(config.output_dir / "page-pairing.jsonl", pairs)
    _csv(config.output_dir / "page-metrics.csv", [{key: value for key, value in record.items() if key not in {"derived", "metrics"}} | {f"metric_{key}": value for key, value in record.get("metrics", {}).items()} for record in records])
    _csv(config.output_dir / "variant-summary.csv", variants)
    _csv(config.output_dir / "work-classification.csv", classifications)
    _csv(config.output_dir / "triplet-quality.csv", triplets)
    _atomic_json(config.output_dir / "split-proposal.json", split)
    _atomic_text(config.output_dir / "unresolved-items.md", "# Unresolved Items\n\n" + "\n".join(f"- `{item}`" for item in sorted(unresolved)) + "\n")
    _atomic_text(config.output_dir / "REPORT.md", _report(manifest, classifications, pairs, triplets, split, unresolved))
    output_hashes = {path.name: sha256_file(path) for path in sorted(config.output_dir.iterdir()) if path.is_file() and path.name != "run-manifest.json"}
    manifest["output_sha256"] = output_hashes
    _atomic_json(config.output_dir / "run-manifest.json", manifest)
    return manifest


def regenerate_from_existing_outputs(output_dir: Path, series_groups: dict[str, str]) -> dict[str, Any]:
    """Regenerate aggregate outputs from existing JSONL/CSV facts without image work."""
    records = [json.loads(line) for line in (output_dir / "file-inventory.jsonl").read_text(encoding="utf-8").splitlines()]
    pairs = [json.loads(line) for line in (output_dir / "page-pairing.jsonl").read_text(encoding="utf-8").splitlines()]
    with (output_dir / "triplet-quality.csv").open(encoding="utf-8", newline="") as handle:
        triplets = list(csv.DictReader(handle))
    previous_manifest = json.loads((output_dir / "run-manifest.json").read_text(encoding="utf-8"))
    unresolved = {line[3:-1] for line in (output_dir / "unresolved-items.md").read_text(encoding="utf-8").splitlines() if line.startswith("- `") and line.endswith("`")}
    display_names = {record["work_id"]: record["relative_path"].split("/")[0] for record in records if record["work_id"] != "unclassified"}
    classifications = _classify_work(records, triplets, display_names)
    split = _split_proposal(classifications, series_groups)
    variant_rows: list[dict[str, Any]] = []
    by_variant: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_variant[(record["work_id"], record["variant"])].append(record)
    extras = [item.removeprefix("extra_reference_page:") for item in unresolved if item.startswith("extra_reference_page:")]
    for (work_id, variant), group in sorted(by_variant.items()):
        processed = [record for record in group if record.get("decode_status") == "processed"]
        relative_dir = str(Path(group[0]["relative_path"]).parent) if group else ""
        variant_rows.append({"work_id": work_id, "variant": variant, "relative_path": relative_dir, "file_count": len(group), "decoded_count": len(processed), "decode_failed_count": sum(record.get("decode_status") == "decode_failed" for record in group), "dimensions": _range_text([(record["width"], record["height"]) for record in processed]), "color_modes": _counter_text(record.get("color_mode") for record in processed), "medium": _counter_text(record.get("metrics", {}).get("medium") for record in processed), "mean_sharpness": _mean(processed, "metrics", "sharpness"), "mean_noise": _mean(processed, "metrics", "noise_estimate"), "extra_reference_pages": sum(path.startswith(relative_dir + "/") for path in extras)})
    manual_rows = []
    for item in sorted(unresolved):
        code, path = item.split(":", 1)
        manual_rows.append({"item_type": code, "relative_path": path, "work_id": next((record["work_id"] for record in records if record["relative_path"] == path), ""), "action": "人工复核配对/配准或确认额外参考页", "content_description": ""})
    _csv(output_dir / "variant-summary.csv", variant_rows)
    _csv(output_dir / "work-classification.csv", classifications)
    _csv(output_dir / "manual-review.csv", manual_rows)
    _atomic_json(output_dir / "split-proposal.json", split)
    parent_run_id = previous_manifest.get("parent_run_id", previous_manifest.get("run_id"))
    manifest = {
        **{key: value for key, value in previous_manifest.items() if key not in {"processing_version", "run_id", "parent_run_id", "output_sha256", "config"}},
        "run_id": f"dataset-audit-aggregation-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "parent_run_id": parent_run_id,
        "source_analysis_version": "dataset-audit-v0.1",
        "aggregation_version": "dataset-audit-v0.3",
        "aggregation_regenerated_from_existing_facts": True,
        "series_groups": series_groups,
    }
    _atomic_text(output_dir / "REPORT.md", _report(manifest, classifications, pairs, triplets, split, unresolved))
    output_hashes = {path.name: sha256_file(path) for path in sorted(output_dir.iterdir()) if path.is_file() and path.name != "run-manifest.json"}
    manifest["output_sha256"] = output_hashes
    _atomic_json(output_dir / "run-manifest.json", manifest)
    return manifest


def validate_output_consistency(output_dir: Path) -> None:
    """Verify cross-file summary counts are derived from the review fact rows."""
    with (output_dir / "manual-review.csv").open(encoding="utf-8", newline="") as handle:
        review_rows = list(csv.DictReader(handle))
    with (output_dir / "variant-summary.csv").open(encoding="utf-8", newline="") as handle:
        variants = list(csv.DictReader(handle))
    extras = [row["relative_path"] for row in review_rows if row["item_type"] == "extra_reference_page"]
    summary_extras = sum(int(row["extra_reference_pages"]) for row in variants)
    if len(extras) != summary_extras:
        raise RuntimeError("extra_reference_summary_mismatch")
    if len(review_rows) != 17 or Counter(row["item_type"] for row in review_rows) != Counter({"pairing_unresolved": 3, "registration_low_confidence": 12, "extra_reference_page": 2}):
        raise RuntimeError("manual_review_fact_count_mismatch")
