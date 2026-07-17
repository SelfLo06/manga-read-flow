#!/usr/bin/env python3
"""Local, review-only automatic typesetting feasibility harness.

The harness intentionally stops at image candidates.  It does not create
product artifacts, QualityIssues, active pointers, or workflow state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from tools.spikes.text_seeded_container_association import goal6_mask_harness as cleaning_mask
from tools.spikes.text_seeded_container_association.goal6_build_calibration import (
    _fragments,
)


FORBIDDEN_LINE_START = frozenset("，。！？：；、）》」』】〕〉…")
FORBIDDEN_LINE_END = frozenset("《（「『【〔〈")
PLACEHOLDER_TEXT = {
    "case-71": {
        "container-001": "别担心，我马上回来。",
        "container-002": "如果现在放弃，就再也没有机会了！",
        "container-003": "你真的决定好了吗？",
        "container-004": "等等，那边好像有什么动静。",
        "container-005": "嗯，我知道了。",
    },
    "case-72": {
        "container-001": "原来你一直都在这里。",
        "container-004": "无论发生什么，我都会陪在你身边。",
        "container-006": "谢谢。",
    },
}


class TypesettingStop(RuntimeError):
    pass


@dataclass(frozen=True)
class LayoutPlan:
    context_id: str
    text: str
    lines: tuple[str, ...]
    font_path: str
    font_size: int
    line_step: int
    positions: tuple[tuple[int, int], ...]
    color: tuple[int, int, int]
    stroke_color: tuple[int, int, int]
    stroke_width: int
    overflow_ratio: float
    minimum_inner_margin: float
    boundary_touch: bool
    contrast_ratio: float
    style: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where(mask)
    if not len(xs):
        raise TypesettingStop("empty layout region")
    return int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)


def _text_size(font: ImageFont.FreeTypeFont, text: str) -> tuple[int, int]:
    left, top, right, bottom = font.getbbox(text or " ")
    return right - left, bottom - top


def _valid_break(text: str, start: int, end: int) -> bool:
    line = text[start:end]
    if not line:
        return False
    if line[0] in FORBIDDEN_LINE_START or line[-1] in FORBIDDEN_LINE_END:
        return False
    return True


def wrap_chinese(text: str, font: ImageFont.FreeTypeFont, max_width: int, max_lines: int) -> tuple[str, ...] | None:
    """Choose punctuation-safe character breaks with a small raggedness DP."""
    paragraphs = text.split("\n")
    all_lines: list[str] = []
    for paragraph in paragraphs:
        if not paragraph:
            all_lines.append("")
            continue
        n = len(paragraph)
        best: list[tuple[float, tuple[str, ...]] | None] = [None] * (n + 1)
        best[0] = (0.0, ())
        for end in range(1, n + 1):
            for start in range(end):
                previous = best[start]
                if previous is None or not _valid_break(paragraph, start, end):
                    continue
                line = paragraph[start:end]
                width, _ = _text_size(font, line)
                if width > max_width:
                    continue
                lines = previous[1] + (line,)
                if len(all_lines) + len(lines) > max_lines:
                    continue
                fullness = width / max(1, max_width)
                cost = previous[0] + (1.0 - fullness) ** 2
                if end == n:
                    cost *= 0.55
                    if len(line) == 1 and n > 1:
                        cost += 2.0
                candidate = (cost, lines)
                if best[end] is None or candidate[0] < best[end][0]:
                    best[end] = candidate
        if best[n] is None:
            return None
        all_lines.extend(best[n][1])
    return tuple(all_lines) if len(all_lines) <= max_lines else None


def _glyph_mask(
    shape: tuple[int, int], lines: Iterable[str], positions: Iterable[tuple[int, int]],
    font: ImageFont.FreeTypeFont, stroke_width: int = 0,
) -> np.ndarray:
    canvas = Image.new("L", (shape[1], shape[0]), 0)
    draw = ImageDraw.Draw(canvas)
    for line, position in zip(lines, positions):
        draw.text(position, line, font=font, fill=255, stroke_width=stroke_width, stroke_fill=255)
    return np.asarray(canvas) > 0


def rectangular_region(region: np.ndarray) -> np.ndarray:
    x0, y0, x1, y1 = _bbox(region)
    output = np.zeros_like(region)
    output[y0:y1, x0:x1] = True
    return output


def _relative_luminance(color: tuple[int, int, int]) -> float:
    channels = []
    for value in color:
        channel = value / 255.0
        channels.append(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    high, low = sorted((_relative_luminance(first), _relative_luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def estimate_style(source: np.ndarray, cleaned: np.ndarray, effective: np.ndarray, region: np.ndarray) -> tuple[tuple[int, int, int], tuple[int, int, int], float]:
    pixels = source[effective]
    if not len(pixels):
        foreground = (0, 0, 0)
    else:
        luminance = 0.2126 * pixels[:, 0] + 0.7152 * pixels[:, 1] + 0.0722 * pixels[:, 2]
        foreground = tuple(int(value) for value in np.median(pixels[luminance <= np.quantile(luminance, 0.45)], axis=0))
    background = tuple(int(value) for value in np.median(cleaned[region], axis=0))
    ratio = contrast_ratio(foreground, background)
    if ratio < 4.5:
        black_ratio = contrast_ratio((0, 0, 0), background)
        white_ratio = contrast_ratio((255, 255, 255), background)
        foreground = (0, 0, 0) if black_ratio >= white_ratio else (255, 255, 255)
        ratio = max(black_ratio, white_ratio)
    stroke = (255, 255, 255) if _relative_luminance(foreground) < 0.5 else (0, 0, 0)
    return foreground, stroke, ratio


def find_layout(
    context_id: str,
    text: str,
    region: np.ndarray,
    font_path: Path,
    color: tuple[int, int, int] = (0, 0, 0),
    stroke_color: tuple[int, int, int] = (255, 255, 255),
    stroke_width_fraction: float = 0.0,
    style: str = "dialogue",
    min_size: int = 11,
    max_size: int = 54,
) -> LayoutPlan | None:
    x0, y0, x1, y1 = _bbox(region)
    center_x = float(np.mean(np.where(region)[1]))
    center_y = float(np.mean(np.where(region)[0]))
    distance = cv2.distanceTransform(region.astype(np.uint8), cv2.DIST_L2, 5)
    max_width = max(1, x1 - x0 - 8)
    for size in range(min(max_size, max(12, y1 - y0)), min_size - 1, -1):
        font = ImageFont.truetype(str(font_path), size)
        _, glyph_height = _text_size(font, "国")
        line_step = max(glyph_height + 2, int(round(size * 1.18)))
        max_lines = max(1, (y1 - y0 - 6) // line_step)
        candidates: list[tuple[float, LayoutPlan]] = []
        seen_lines: set[tuple[str, ...]] = set()
        for width_fraction in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5):
            lines = wrap_chinese(text, font, max(1, int(max_width * width_fraction)), max_lines)
            if not lines or lines in seen_lines:
                continue
            seen_lines.add(lines)
            total_height = (len(lines) - 1) * line_step + glyph_height
            line_widths = [_text_size(font, line)[0] for line in lines]
            for dx in (0, -3, 3, -6, 6):
                for dy in (0, -4, 4, -8, 8):
                    first_y = int(round(center_y - total_height / 2)) + dy
                    positions = tuple(
                        (int(round(center_x + dx - width / 2)), first_y + index * line_step)
                        for index, width in enumerate(line_widths)
                    )
                    stroke_width = int(round(size * stroke_width_fraction))
                    glyph = _glyph_mask(region.shape, lines, positions, font, stroke_width)
                    glyph_pixels = int(glyph.sum())
                    if not glyph_pixels or np.any(glyph & ~region):
                        continue
                    margin = float(distance[glyph].min())
                    if margin < 2.0:
                        continue
                    width_balance = float(np.std(line_widths) / max(1.0, np.mean(line_widths)))
                    score = margin - 0.08 * abs(dx) - 0.05 * abs(dy) - 0.5 * width_balance
                    candidates.append(
                        (
                            score,
                            LayoutPlan(
                                context_id, text, lines, str(font_path), size, line_step, positions, color,
                                stroke_color, stroke_width, 0.0, margin, False, 0.0, style,
                            ),
                        )
                    )
        if candidates:
            return max(candidates, key=lambda item: item[0])[1]
    return None


def render_plans(base: np.ndarray, plans: Iterable[LayoutPlan], scale: int = 4) -> np.ndarray:
    large = Image.fromarray(base).resize((base.shape[1] * scale, base.shape[0] * scale), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(large)
    for plan in plans:
        font = ImageFont.truetype(plan.font_path, plan.font_size * scale)
        for line, (x, y) in zip(plan.lines, plan.positions):
            draw.text(
                (x * scale, y * scale), line, font=font, fill=plan.color,
                stroke_width=plan.stroke_width * scale, stroke_fill=plan.stroke_color,
            )
    return np.asarray(large.resize((base.shape[1], base.shape[0]), Image.Resampling.LANCZOS))


def _comparison(images: tuple[np.ndarray, ...], labels: tuple[str, ...]) -> Image.Image:
    height, width = images[0].shape[:2]
    header = 34
    sheet = Image.new("RGB", (width * len(images), height + header), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (image, label) in enumerate(zip(images, labels)):
        sheet.paste(Image.fromarray(image), (index * width, header))
        draw.text((index * width + 8, 9), label, fill=(0, 0, 0))
    return sheet


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypesettingStop(f"JSON root must be an object: {path}")
    return payload


def recover_context_masks(source: np.ndarray, overlay: np.ndarray, asset: dict[str, Any]) -> dict[str, np.ndarray]:
    """Recover frozen coarse contexts without rerunning B1.

    Goal 6 painted every context pixel as either safe or protected, so changed
    overlay pixels form the coarse-context union. Frozen S1 group polygons split
    that union deterministically. This only adapts old evidence; it is not a
    product input contract.
    """
    if overlay.shape != source.shape:
        raise TypesettingStop("source and context overlay shapes differ")
    delta = np.max(np.abs(overlay.astype(np.int16) - source.astype(np.int16)), axis=2)
    union = delta >= 2
    union = cv2.morphologyEx(
        union.astype(np.uint8), cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
    ).astype(bool)
    fragments_by_id = {item.fragment_id: item for item in _fragments(asset)}
    groups = tuple(asset.get("groups", ()))
    if not groups or not union.any():
        raise TypesettingStop("cannot recover context masks without groups and overlay pixels")
    best_distance = np.full(union.shape, np.inf, dtype=np.float32)
    owner = np.full(union.shape, -1, dtype=np.int16)
    for index, group in enumerate(groups):
        fragment_ids = group.get("ordered_fragment_ids", ())
        seed = cleaning_mask.polygon_mask(
            union.shape, tuple(fragments_by_id[item] for item in fragment_ids if item in fragments_by_id)
        )
        if not seed.any():
            raise TypesettingStop(f"group has no recoverable seed: {group.get('group_id')}")
        distance = cv2.distanceTransform((~seed).astype(np.uint8), cv2.DIST_L2, 3)
        update = union & (distance < best_distance)
        best_distance[update] = distance[update]
        owner[update] = index
    return {
        f"container-{index + 1:03d}": union & (owner == index)
        for index in range(len(groups)) if np.any(union & (owner == index))
    }


def run(
    root: Path, s1_path: Path, goal5_lock_path: Path, mask_lock_path: Path,
    cleaned_dir: Path, output_dir: Path, regular_font: Path, bold_font: Path,
    asset_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    if output_dir.exists():
        raise TypesettingStop("output directory already exists")
    for path in (s1_path, goal5_lock_path, mask_lock_path, regular_font, bold_font):
        if not path.is_file():
            raise TypesettingStop(f"missing input: {path}")
    s1 = _load(s1_path)
    if s1.get("status") != "completed" or s1.get("input_hashes_unchanged") is not True:
        raise TypesettingStop("S1 input is not complete and hash-stable")
    mask_lock = _load(mask_lock_path)
    if mask_lock.get("selected_policy") != "P0_conservative":
        raise TypesettingStop("unexpected cleaning mask policy")
    _load(goal5_lock_path)  # Hash-locked provenance only; B1 must not rerun here.
    output_dir.mkdir(parents=True)
    records = []
    for asset in s1.get("assets", ()):
        asset_id = asset["asset_id"]
        if asset_id not in PLACEHOLDER_TEXT or (asset_ids and asset_id not in asset_ids):
            continue
        source_path = root / asset["relative_path"]
        cleaned_path = cleaned_dir / asset_id / "candidate-e1-only.png"
        overlay_path = cleaned_dir / asset_id / "mask-safe-overlay.png"
        if not cleaned_path.is_file() or not overlay_path.is_file():
            raise TypesettingStop(f"missing cleaned page or frozen context overlay: {asset_id}")
        source = np.asarray(Image.open(source_path).convert("RGB"))
        cleaned = np.asarray(Image.open(cleaned_path).convert("RGB"))
        overlay = np.asarray(Image.open(overlay_path).convert("RGB"))
        source_hash_before = sha256(source_path)
        recovered = recover_context_masks(source, overlay, asset)
        contexts = [(context_id, recovered[context_id]) for context_id in PLACEHOLDER_TEXT[asset_id] if context_id in recovered]
        arms: dict[str, list[LayoutPlan]] = {"R0": [], "R1": [], "R2": []}
        failures: list[dict[str, str]] = []
        changed_by_cleaning = np.any(source != cleaned, axis=2)
        for context_id, coarse_region in contexts:
            text = PLACEHOLDER_TEXT[asset_id].get(context_id)
            if text is None:
                raise TypesettingStop(f"missing frozen probe text: {asset_id}/{context_id}")
            # Goal 6's ``safe`` is a cleaning write region and intentionally has
            # structure holes.  It is not a typesetting region.  For this spike
            # the next valid input in the priority chain is the coarse container
            # mask, conservatively inset before laying out glyphs.
            layout_region = cleaning_mask.erode(coarse_region, 8)
            if not layout_region.any():
                failures.append({"context_id": context_id, "reason": "empty_inset_container_region"})
                continue
            effective = changed_by_cleaning & coarse_region
            if not effective.any():
                raise TypesettingStop(f"E1 context has no traceable cleaning writeback: {asset_id}/{context_id}")
            r0 = find_layout(context_id, text, rectangular_region(layout_region), regular_font)
            r1 = find_layout(context_id, text, layout_region, regular_font)
            foreground, stroke, ratio = estimate_style(source, cleaned, effective, layout_region)
            background_std = float(np.std(cleaned[layout_region]))
            emphasis = "！" in text or "!" in text
            r2 = find_layout(
                context_id, text, layout_region, bold_font if emphasis else regular_font,
                foreground, stroke, 0.04 if background_std > 28.0 else 0.0,
                "emphasis" if emphasis else "dialogue",
            )
            for arm, plan in (("R0", r0), ("R1", r1), ("R2", r2)):
                if plan is None:
                    failures.append({"context_id": context_id, "reason": f"{arm}_no_fit"})
                else:
                    arms[arm].append(LayoutPlan(**{**asdict(plan), "contrast_ratio": ratio if arm == "R2" else contrast_ratio((0, 0, 0), tuple(int(v) for v in np.median(cleaned[layout_region], axis=0))) }))
        rendered = {arm: render_plans(cleaned, plans) for arm, plans in arms.items()}
        page_dir = output_dir / asset_id
        page_dir.mkdir()
        Image.fromarray(source).save(page_dir / "source.png")
        Image.fromarray(cleaned).save(page_dir / "cleaned-input.png")
        for arm, image in rendered.items():
            Image.fromarray(image).save(page_dir / f"{arm.lower()}.png")
        _comparison(
            (cleaned, rendered["R0"], rendered["R1"], rendered["R2"]),
            ("CLEANED INPUT", "R0 BBOX", "R1 MASK-AWARE", "R2 STYLE-AWARE"),
        ).save(page_dir / "comparison.png")
        record = {
            "asset_id": asset_id,
            "probe_text_is_translation": False,
            "eligible_e1_contexts": len(contexts),
            "arms": {arm: [asdict(plan) for plan in plans] for arm, plans in arms.items()},
            "failures": failures,
            "source_sha256_before": source_hash_before,
            "source_sha256_after": sha256(source_path),
            "context_overlay_sha256": sha256(overlay_path),
            "context_source": "recovered_from_goal6_overlay_with_s1_group_seeds",
        }
        (page_dir / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        records.append(record)
    expected_contexts = sum(len(PLACEHOLDER_TEXT[item]) for item in (asset_ids or tuple(PLACEHOLDER_TEXT)))
    if sum(item["eligible_e1_contexts"] for item in records) != expected_contexts:
        raise TypesettingStop(f"frozen scope must contain exactly {expected_contexts} E1 contexts")
    payload = {
        "schema_version": "typesetting-feasibility-v0.1",
        "purpose": "visual feasibility only; no workflow integration or AUTO_ACCEPT",
        "probe_text_is_translation": False,
        "inputs": {
            "s1_sha256": sha256(s1_path),
            "goal5_lock_sha256": sha256(goal5_lock_path),
            "mask_lock_sha256": sha256(mask_lock_path),
            "regular_font": str(regular_font),
            "regular_font_sha256": sha256(regular_font),
            "bold_font": str(bold_font),
            "bold_font_sha256": sha256(bold_font),
        },
        "records": records,
    }
    (output_dir / "matrix.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--s1", type=Path, required=True)
    parser.add_argument("--goal5-lock", type=Path, required=True)
    parser.add_argument("--mask-lock", type=Path, required=True)
    parser.add_argument("--cleaned-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--regular-font", type=Path, required=True)
    parser.add_argument("--bold-font", type=Path, required=True)
    parser.add_argument("--asset-id", action="append", choices=tuple(PLACEHOLDER_TEXT))
    args = parser.parse_args()
    try:
        payload = run(
            args.root.resolve(), args.s1.resolve(), args.goal5_lock.resolve(), args.mask_lock.resolve(),
            args.cleaned_dir.resolve(), args.output_dir.resolve(), args.regular_font.resolve(), args.bold_font.resolve(),
            tuple(args.asset_id or ()),
        )
    except (OSError, ValueError, json.JSONDecodeError, TypesettingStop, cleaning_mask.Goal6Stop) as error:
        print(f"STOP: {error}")
        return 2
    print(json.dumps({"status": "READY_FOR_HUMAN_REVIEW", "pages": len(payload["records"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
