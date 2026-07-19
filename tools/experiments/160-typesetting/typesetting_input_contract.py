#!/usr/bin/env python3
"""Two-page Typesetting input-contract and validator-grounding spike.

This runner is intentionally local and evidence-only. It does not integrate
providers, repositories, artifacts, quality issues, or workflow state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from tools.experiments.ocr_130.detection_ocr.spike import MangaOcrRunner
from tools.experiments.translation_140.page_translation import spike as translation


ROOT = Path(__file__).resolve().parents[3]
PROMPT_PATH = ROOT / "tools/experiments/140-translation/page_translation/prompts/system-v1.md"
REPAIR_PROMPT_PATH = ROOT / "tools/experiments/140-translation/page_translation/prompts/repair-system-v1.md"
SCHEMA_PATH = ROOT / "data/local/datasets/140-translation/page-translation-v0.1/schema.json"


class ContractStop(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContractStop(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    translation.assert_no_secret_text(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def git_value(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


@dataclass
class StageTiming:
    stage: str
    status: str
    duration_ms: int
    reason: str | None = None
    source_run: str | None = None


class Timings:
    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.records: list[StageTiming] = []

    def reused(self, stage: str, reason: str) -> None:
        self.records.append(StageTiming(stage, "reused", 0, reason))

    def imported(self, stage: str, duration_ms: int, source_run: Path) -> None:
        self.records.append(
            StageTiming(stage, "completed_prior_attempt", duration_ms, "validated checkpoint reused", str(source_run))
        )

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        except Exception as error:
            self.records.append(StageTiming(name, "failed", round((time.perf_counter() - start) * 1000), type(error).__name__))
            raise
        else:
            self.records.append(StageTiming(name, "completed", round((time.perf_counter() - start) * 1000)))

    def payload(self) -> dict[str, Any]:
        records = [record.__dict__ for record in self.records]
        total = round((time.perf_counter() - self.started) * 1000)
        return {
            "clock": "time.perf_counter monotonic wall time",
            "stages": records,
            "cumulative_pipeline_time_ms": sum(item["duration_ms"] for item in records),
            "current_attempt_wall_time_ms": total,
            "total_wall_time_ms": sum(item["duration_ms"] for item in records),
        }


def import_checkpoint(
    source_run: Path, run_dir: Path, current_input_lock: dict[str, Any], timings: Timings,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_lock = load_json(source_run / "input-lock.json")
    for key in ("s1_sha256", "prompt_sha256", "repair_prompt_sha256", "sources"):
        if source_lock.get(key) != current_input_lock.get(key):
            raise ContractStop(f"checkpoint input lock mismatch: {key}")
    source_timings = load_json(source_run / "timings.json")
    by_stage = {item["stage"]: item for item in source_timings.get("stages", ())}
    for stage in ("ocr_model_init", "ocr", "translation", "provenance"):
        item = by_stage.get(stage)
        if not item or item.get("status") != "completed":
            raise ContractStop(f"checkpoint stage is not reusable: {stage}")
        timings.imported(stage, int(item["duration_ms"]), source_run)
    ocr_payload = load_json(source_run / "ocr-results.json")
    translation_payload = load_json(source_run / "translation-results.json")
    ledger = load_json(source_run / "provenance-ledger.json")
    if ledger.get("completeness", {}).get("coverage") != 1.0:
        raise ContractStop("checkpoint provenance is incomplete")
    for directory in ("ocr-crops", "translation-raw"):
        if (source_run / directory).exists():
            shutil.copytree(source_run / directory, run_dir / directory)
    write_json(run_dir / "ocr-results.json", ocr_payload)
    write_json(run_dir / "translation-results.json", translation_payload)
    write_json(run_dir / "provenance-ledger.json", ledger)
    return ocr_payload, translation_payload, ledger


def union_bbox(fragments: list[dict[str, Any]], shape: tuple[int, int], padding: int = 8) -> dict[str, int]:
    x0 = max(0, min(int(item["bbox"]["x"]) for item in fragments) - padding)
    y0 = max(0, min(int(item["bbox"]["y"]) for item in fragments) - padding)
    x1 = min(shape[1], max(int(item["bbox"]["x"] + item["bbox"]["width"]) for item in fragments) + padding)
    y1 = min(shape[0], max(int(item["bbox"]["y"] + item["bbox"]["height"]) for item in fragments) + padding)
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


def split_group_segments(group: dict[str, Any], fragments_by_id: dict[str, dict[str, Any]]) -> list[list[str]]:
    """Preserve obvious vertical baseline jumps as separate paragraph segments."""
    ordered = [item for item in group.get("ordered_fragment_ids", ()) if item in fragments_by_id]
    if not ordered:
        raise ContractStop(f"group has no traceable fragments: {group.get('group_id')}")
    if group.get("orientation") != "vertical" or len(ordered) == 1:
        return [ordered]
    heights = [float(fragments_by_id[item]["bbox"]["height"]) for item in ordered]
    threshold = max(48.0, float(np.median(heights)) * 0.65)
    segments: list[list[str]] = [[ordered[0]]]
    anchor_tops: list[float] = [float(fragments_by_id[ordered[0]]["bbox"]["y"])]
    for fragment_id in ordered[1:]:
        top = float(fragments_by_id[fragment_id]["bbox"]["y"])
        if abs(top - float(np.median(anchor_tops))) > threshold:
            segments.append([fragment_id])
            anchor_tops = [top]
        else:
            segments[-1].append(fragment_id)
            anchor_tops.append(top)
    return segments


def build_segments(asset: dict[str, Any]) -> list[dict[str, Any]]:
    fragments_by_id = {item["fragment_id"]: item for item in asset.get("fragments", ())}
    segments: list[dict[str, Any]] = []
    reading_order = 0
    for group_index, group in enumerate(asset.get("groups", ()), start=1):
        for segment_index, fragment_ids in enumerate(split_group_segments(group, fragments_by_id), start=1):
            reading_order += 1
            fragments = [fragments_by_id[item] for item in fragment_ids]
            segment_id = f"{group['group_id']}__s{segment_index:02d}"
            segments.append(
                {
                    "segment_id": segment_id,
                    "text_group_id": group["group_id"],
                    "group_index": group_index,
                    "segment_index": segment_index,
                    "reading_order": reading_order,
                    "orientation": group.get("orientation"),
                    "fragment_ids": fragment_ids,
                    "bbox": union_bbox(fragments, (int(asset["height"]), int(asset["width"]))),
                }
            )
    traced = [item for segment in segments for item in segment["fragment_ids"]]
    expected = [item["fragment_id"] for item in asset.get("fragments", ())]
    if sorted(traced) != sorted(expected) or len(traced) != len(set(traced)):
        raise ContractStop(f"fragment trace is not complete and one-to-one: {asset['asset_id']}")
    return segments


def crop(image: Image.Image, bbox: dict[str, int], path: Path) -> None:
    x, y = bbox["x"], bbox["y"]
    image.crop((x, y, x + bbox["width"], y + bbox["height"])).save(path, "PNG")


def run_ocr(runner: MangaOcrRunner, root: Path, assets: list[dict[str, Any]], run_dir: Path) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    crops_dir = run_dir / "ocr-crops"
    crops_dir.mkdir()
    for asset in assets:
        image_path = root / asset["relative_path"]
        with Image.open(image_path) as source:
            image = source.convert("RGB")
            segments = build_segments(asset)
            results = []
            for segment in segments:
                crop_path = crops_dir / f"{segment['segment_id']}.png"
                crop(image, segment["bbox"], crop_path)
                result = runner.recognize(crop_path)
                text = str(result.get("raw_text", "")).strip()
                results.append(
                    {
                        **segment,
                        "ocr_result_id": f"ocr::{segment['segment_id']}",
                        "source_text": text,
                        "ocr_status": "completed" if text else "empty",
                        "ocr_error": result.get("error"),
                        "ocr_duration_ms": round(float(result.get("duration_sec", 0.0)) * 1000),
                        "crop_relative_path": str(crop_path.relative_to(run_dir)),
                        "crop_sha256": sha256(crop_path),
                    }
                )
        pages.append({"asset_id": asset["asset_id"], "segments": results})
    empty = [item["segment_id"] for page in pages for item in page["segments"] if not item["source_text"]]
    if empty:
        raise ContractStop("OCR returned empty segments: " + ", ".join(empty))
    return {"schema_version": "typesetting-input-ocr-v1", "pages": pages}


def translate_pages(ocr_payload: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    config = translation.require_api_config()
    client = translation.OpenAICompatibleClient(config)
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    repair_prompt = REPAIR_PROMPT_PATH.read_text(encoding="utf-8")
    schema = load_json(SCHEMA_PATH)
    pages = []
    raw_dir = run_dir / "translation-raw"
    raw_dir.mkdir()
    for page in ocr_payload["pages"]:
        payload = {
            "page_id": page["asset_id"],
            "source_language": "ja",
            "target_language": "zh-Hans",
            "blocks": [
                {
                    "text_block_id": item["segment_id"],
                    "reading_order": item["reading_order"],
                    "group_id": item["text_group_id"],
                    "source_text": item["source_text"],
                }
                for item in page["segments"]
            ],
            "glossary": [],
            "previous_context": [],
        }
        request_hash = translation.sha256_bytes(translation.dumps_json(payload).encode("utf-8"))
        first = client.complete(translation.prompt_messages(system_prompt, payload))
        write_json(raw_dir / f"{page['asset_id']}-first.json", first.raw or {"error": first.error_classification})
        parsed, parse_errors = translation.parse_model_json(first.content) if first.ok else (None, [])
        validation = translation.validate_translation_output(parsed, payload)
        validation["errors"] = sorted(set(validation["errors"] + parse_errors))
        validation["valid"] = not validation["errors"]
        retry = {"attempted": False, "recovered": False, "latency_ms": 0}
        total_latency = first.latency_ms
        input_tokens = first.input_tokens
        output_tokens = first.output_tokens
        if first.ok and any(item in translation.RETRYABLE_ERRORS for item in validation["errors"]):
            retry_result = client.complete(
                translation.repair_messages(repair_prompt, payload, first.content, schema, validation["errors"])
            )
            write_json(raw_dir / f"{page['asset_id']}-repair.json", retry_result.raw or {"error": retry_result.error_classification})
            repaired, repair_parse_errors = translation.parse_model_json(retry_result.content) if retry_result.ok else (None, [])
            repair_validation = translation.validate_translation_output(repaired, payload)
            repair_validation["errors"] = sorted(set(repair_validation["errors"] + repair_parse_errors))
            repair_validation["valid"] = not repair_validation["errors"]
            retry = {"attempted": True, "recovered": repair_validation["valid"], "latency_ms": retry_result.latency_ms}
            total_latency += retry_result.latency_ms
            input_tokens = translation.sum_tokens(input_tokens, retry_result.input_tokens)
            output_tokens = translation.sum_tokens(output_tokens, retry_result.output_tokens)
            if repair_validation["valid"]:
                parsed, validation = repaired, repair_validation
        if not first.ok or not validation["valid"] or parsed is None:
            raise ContractStop(f"translation failed for {page['asset_id']}: {first.error_classification or validation['errors']}")
        pages.append(
            {
                "asset_id": page["asset_id"],
                "request_hash": request_hash,
                "provider": "openai-compatible",
                "model": config["model"],
                "latency_ms": total_latency,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "validation": validation,
                "retry": retry,
                "translations": parsed["translations"],
            }
        )
    return {
        "schema_version": "typesetting-input-translation-v1",
        "prompt_sha256": sha256(PROMPT_PATH),
        "repair_prompt_sha256": sha256(REPAIR_PROMPT_PATH),
        "pages": pages,
    }


def context_map(diagnostics_dir: Path, asset_id: str) -> dict[str, dict[str, Any]]:
    payload = load_json(diagnostics_dir / asset_id / "context-writeback-check.json")
    return {item["context_id"]: item for item in payload["contexts"]}


def build_ledger(
    assets: list[dict[str, Any]], ocr_payload: dict[str, Any], translation_payload: dict[str, Any], diagnostics_dir: Path,
) -> dict[str, Any]:
    ocr_pages = {item["asset_id"]: item for item in ocr_payload["pages"]}
    translated_pages = {item["asset_id"]: item for item in translation_payload["pages"]}
    pages = []
    fragment_rows = []
    for asset in assets:
        asset_id = asset["asset_id"]
        contexts = context_map(diagnostics_dir, asset_id)
        translations = {
            item["text_block_id"]: item for item in translated_pages[asset_id]["translations"]
        }
        blocks = []
        if len(asset.get("groups", ())) != len(contexts):
            raise ContractStop(f"group/context cardinality mismatch: {asset_id}")
        for segment in ocr_pages[asset_id]["segments"]:
            context_id = f"container-{segment['group_index']:03d}"
            context = contexts[context_id]
            translated = translations.get(segment["segment_id"])
            if translated is None:
                raise ContractStop(f"missing translated segment: {segment['segment_id']}")
            eligible = context["risk"] == "E1" and context["application"] == "E1_ONLY"
            block_id = f"typeset::{segment['segment_id']}" if eligible else None
            exclusion = None if eligible else f"{context['risk']}::{context['application']}"
            region_id = f"region::{asset_id}::{context_id}" if eligible else None
            block = {
                "asset_id": asset_id,
                "fragment_ids": segment["fragment_ids"],
                "text_group_id": segment["text_group_id"],
                "segment_id": segment["segment_id"],
                "ocr_result_id": segment["ocr_result_id"],
                "source_text": segment["source_text"],
                "translation_segment_id": f"translation::{segment['segment_id']}",
                "translation_text": translated["translation_text"],
                "translation_uncertainty_flags": translated["uncertainty_flags"],
                "container_id": context_id,
                "cleaning_risk": context["risk"],
                "cleaning_decision": context["decision"],
                "cleaning_application": context["application"],
                "typesetting_block_id": block_id,
                "typesetting_region_id": region_id,
                "status": "eligible" if eligible else "excluded",
                "exclusion_reason": exclusion,
                "reading_order": segment["reading_order"],
            }
            blocks.append(block)
            for fragment_id in segment["fragment_ids"]:
                fragment_rows.append(
                    {
                        "asset_id": asset_id,
                        "fragment_id": fragment_id,
                        "text_group_id": segment["text_group_id"],
                        "segment_id": segment["segment_id"],
                        "container_id": context_id,
                        "typesetting_block_id": block_id,
                        "status": block["status"],
                        "exclusion_reason": exclusion,
                    }
                )
        pages.append({"asset_id": asset_id, "blocks": blocks})
    expected = {(asset["asset_id"], item["fragment_id"]) for asset in assets for item in asset["fragments"]}
    traced = [(item["asset_id"], item["fragment_id"]) for item in fragment_rows]
    if set(traced) != expected or len(traced) != len(set(traced)):
        raise ContractStop("ledger does not trace every source fragment exactly once")
    return {
        "schema_version": "typesetting-provenance-ledger-v1",
        "pages": pages,
        "fragment_rows": fragment_rows,
        "completeness": {
            "source_fragment_count": len(expected),
            "traced_fragment_count": len(traced),
            "coverage": 1.0,
            "duplicate_trace_count": len(traced) - len(set(traced)),
        },
    }


def fill_external_contour(component: np.ndarray) -> np.ndarray:
    contours, _ = cv2.findContours(component.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    output = np.zeros_like(component, dtype=np.uint8)
    cv2.drawContours(output, contours, -1, 1, thickness=cv2.FILLED)
    return output.astype(bool)


def extract_bubble_region(image: np.ndarray, seed_bbox: dict[str, int]) -> np.ndarray:
    """Extract the light interior enclosed by nearby dark line art.

    A bright-pixel component is not sufficient on manga pages: the white page
    background and every white bubble may be one component through antialiased
    one-pixel gaps.  Treat dark line art as a dilated barrier instead, then pick
    the enclosed free-space component with the greatest seed overlap.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    barrier = cv2.dilate(
        (gray < 150).astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
        iterations=1,
    )
    candidate = barrier == 0
    _, labels = cv2.connectedComponents(candidate.astype(np.uint8), connectivity=8)
    x, y, width, height = (seed_bbox[key] for key in ("x", "y", "width", "height"))
    window = labels[y : y + height, x : x + width]
    values, frequencies = np.unique(window[window > 0], return_counts=True)
    if not len(values):
        raise ContractStop("no bright bubble component overlaps text seed")
    label = int(values[int(np.argmax(frequencies))])
    component = labels == label
    region = cv2.erode(
        component.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)), iterations=1,
    ).astype(bool)
    area = int(region.sum())
    if area == 0 or area > image.shape[0] * image.shape[1] * 0.18:
        raise ContractStop(f"implausible bubble region area: {area}")
    return region


def mask_sha256(mask: np.ndarray) -> str:
    return hashlib.sha256(np.packbits(mask.reshape(-1)).tobytes()).hexdigest()


def save_mask(mask: np.ndarray, path: Path) -> None:
    Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L").save(path)


def construct_regions(
    root: Path, cleaned_dir: Path, assets: list[dict[str, Any]], ledger: dict[str, Any], run_dir: Path,
) -> dict[str, Any]:
    regions_dir = run_dir / "regions"
    regions_dir.mkdir()
    pages = []
    ledger_pages = {item["asset_id"]: item for item in ledger["pages"]}
    for asset in assets:
        asset_id = asset["asset_id"]
        cleaned_path = cleaned_dir / asset_id / "candidate-e1-only.png"
        image = np.asarray(Image.open(cleaned_path).convert("RGB"))
        groups = {item["group_id"]: item for item in asset["groups"]}
        page_regions = []
        for block in ledger_pages[asset_id]["blocks"]:
            if block["status"] != "eligible":
                continue
            # Multiple segments may intentionally share one container region.
            if any(item["region_id"] == block["typesetting_region_id"] for item in page_regions):
                continue
            group = groups[block["text_group_id"]]
            try:
                region = extract_bubble_region(image, group["bbox"])
            except ContractStop as error:
                raise ContractStop(
                    f"{asset_id}/{block['container_id']}/{block['text_group_id']}: {error}"
                ) from error
            filename = f"{asset_id}__{block['container_id']}.png"
            save_mask(region, regions_dir / filename)
            page_regions.append(
                {
                    "region_id": block["typesetting_region_id"],
                    "container_id": block["container_id"],
                    "text_group_ids": sorted(
                        {item["text_group_id"] for item in ledger_pages[asset_id]["blocks"] if item["container_id"] == block["container_id"]}
                    ),
                    "segment_ids": [
                        item["segment_id"] for item in ledger_pages[asset_id]["blocks"]
                        if item["container_id"] == block["container_id"] and item["status"] == "eligible"
                    ],
                    "mask_relative_path": str((regions_dir / filename).relative_to(run_dir)),
                    "mask_sha256": mask_sha256(region),
                    "pixel_count": int(region.sum()),
                    "mask": region,
                }
            )
        pages.append({"asset_id": asset_id, "cleaned_path": str(cleaned_path), "regions": page_regions})
    return {"schema_version": "typesetting-region-candidate-v1", "pages": pages}


def validate_glyph(region: np.ndarray, glyph: np.ndarray, region_id: str, region_hash: str) -> dict[str, Any]:
    if region.shape != glyph.shape or not glyph.any():
        raise ContractStop("invalid glyph validation input")
    overflow = glyph & ~region
    distance = cv2.distanceTransform(region.astype(np.uint8), cv2.DIST_L2, 5)
    inside = glyph & region
    margin = float(distance[inside].min()) if inside.any() else 0.0
    overflow_pixels = int(overflow.sum())
    return {
        "region_id": region_id,
        "region_sha256": region_hash,
        "glyph_pixels": int(glyph.sum()),
        "overflow_pixels": overflow_pixels,
        "overflow_ratio": overflow_pixels / int(glyph.sum()),
        "minimum_inner_margin": margin,
        "boundary_touch": bool(margin < 2.0),
        "passed": bool(overflow_pixels == 0 and margin >= 2.0),
    }


def safe_probe(region: np.ndarray) -> np.ndarray:
    distance = cv2.distanceTransform(region.astype(np.uint8), cv2.DIST_L2, 5)
    y, x = np.unravel_index(int(np.argmax(distance)), distance.shape)
    probe = np.zeros_like(region)
    probe[max(0, y - 1) : y + 2, max(0, x - 1) : x + 2] = True
    return probe


def run_validator(region_payload: dict[str, Any]) -> dict[str, Any]:
    pages = []
    all_negative_rejected = True
    for page in region_payload["pages"]:
        tests = []
        regions = page["regions"]
        for index, item in enumerate(regions):
            region = item["mask"]
            positive = safe_probe(region)
            result = validate_glyph(region, positive, item["region_id"], item["mask_sha256"])
            tests.append({"test": "safe_inside", "expected": "PASS", **result})

            overflow = positive.copy()
            outside = np.argwhere(~region)
            oy, ox = outside[np.argmin((outside[:, 0] - np.mean(np.where(region)[0])) ** 2 + (outside[:, 1] - np.mean(np.where(region)[1])) ** 2)]
            overflow[int(oy), int(ox)] = True
            result = validate_glyph(region, overflow, item["region_id"], item["mask_sha256"])
            tests.append({"test": "deliberate_overflow", "expected": "REJECT", **result})
            all_negative_rejected &= not result["passed"]

            eroded = cv2.erode(region.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=1).astype(bool)
            boundary = region & ~eroded
            touch = np.zeros_like(region)
            by, bx = np.argwhere(boundary)[0]
            touch[int(by), int(bx)] = True
            result = validate_glyph(region, touch, item["region_id"], item["mask_sha256"])
            tests.append({"test": "deliberate_boundary_touch", "expected": "REJECT", **result})
            all_negative_rejected &= not result["passed"]

            if len(regions) > 1:
                wrong = safe_probe(regions[(index + 1) % len(regions)]["mask"])
                result = validate_glyph(region, wrong, item["region_id"], item["mask_sha256"])
                tests.append({"test": "wrong_container", "expected": "REJECT", **result})
                all_negative_rejected &= not result["passed"]
        pages.append({"asset_id": page["asset_id"], "tests": tests})
    return {
        "schema_version": "typesetting-validator-grounding-v1",
        "pages": pages,
        "all_negative_cases_rejected": all_negative_rejected,
        "all_positive_cases_passed": all(
            item["passed"] for page in pages for item in page["tests"] if item["test"] == "safe_inside"
        ),
    }


def public_regions(region_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": region_payload["schema_version"],
        "pages": [
            {
                "asset_id": page["asset_id"],
                "cleaned_path": page["cleaned_path"],
                "regions": [{key: value for key, value in item.items() if key != "mask"} for item in page["regions"]],
            }
            for page in region_payload["pages"]
        ],
    }


def visualize(
    assets: list[dict[str, Any]], cleaned_dir: Path, ledger: dict[str, Any], region_payload: dict[str, Any], run_dir: Path,
    font_path: Path,
) -> None:
    overlay_dir = run_dir / "overlays"
    overlay_dir.mkdir()
    pages = {item["asset_id"]: item for item in ledger["pages"]}
    region_pages = {item["asset_id"]: item for item in region_payload["pages"]}
    font = ImageFont.truetype(str(font_path), 18)
    for asset in assets:
        asset_id = asset["asset_id"]
        image = np.asarray(Image.open(cleaned_dir / asset_id / "candidate-e1-only.png").convert("RGB"))
        canvas = image.astype(np.float32)
        for item in region_pages[asset_id]["regions"]:
            canvas[item["mask"]] = canvas[item["mask"]] * 0.72 + np.asarray((30, 190, 80)) * 0.28
        rendered = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8))
        draw = ImageDraw.Draw(rendered)
        groups = {item["group_id"]: item for item in asset["groups"]}
        for block in pages[asset_id]["blocks"]:
            bbox = groups[block["text_group_id"]]["bbox"]
            x, y = int(bbox["x"]), int(bbox["y"])
            color = (25, 120, 40) if block["status"] == "eligible" else (210, 55, 45)
            label = f"{block['container_id']} {block['segment_id'].split('__')[-1]} {block['cleaning_risk']}"
            draw.rectangle((x, max(0, y - 24), x + max(190, len(label) * 11), y), fill=(255, 255, 255))
            draw.text((x + 2, max(0, y - 22)), label, font=font, fill=color)
        rendered.save(overlay_dir / f"{asset_id}-regions-and-provenance.png")


def write_form(ledger: dict[str, Any], run_dir: Path) -> None:
    pages = {item["asset_id"]: item for item in ledger["pages"]}
    lines = [
        "# Typesetting Input Contract & Validator Grounding 审查表",
        "",
        "只评价 region、段落映射和真实 OCR/译文对应关系；不评价本轮排版美学。每题只选一个。",
        "",
    ]
    for asset_id in ("case-71", "case-72"):
        lines.extend([f"## {asset_id}", "", f"![{asset_id}](overlays/{asset_id}-regions-and-provenance.png)", ""])
        if asset_id == "case-71":
            lines.extend([
                "container-002 的上下文字是否已作为两个独立 segment 保存：",
                "", "- [ ] YES", "- [ ] NO", "- [ ] UNCERTAIN", "",
            ])
        lines.extend([
            "绿色 typesetting region 是否都位于对应真实气泡内部：",
            "", "- [ ] YES", "- [ ] NO", "- [ ] UNCERTAIN", "",
            "OCR 与真实译文是否对应原文字段（允许 OCR 有错，但不得串块）：",
            "", "- [ ] YES", "- [ ] NO", "- [ ] UNCERTAIN", "",
            "备注：", "",
        ])
        for block in pages[asset_id]["blocks"]:
            lines.append(
                f"- `{block['segment_id']}` → `{block['container_id']}` / {block['cleaning_risk']} / "
                f"OCR：{block['source_text']} / 译文：{block['translation_text']} / {block['status']}"
            )
        lines.append("")
    lines.extend([
        "## 总体", "",
        "是否允许进入字号/换行/留白优化：", "",
        "- [ ] GO", "- [ ] GO_WITH_CHANGES", "- [ ] NO_GO", "", "备注：", "",
    ])
    (run_dir / "FORM.md").write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> Path:
    run_dir = args.output_dir.resolve()
    if run_dir.exists():
        raise ContractStop(f"output directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    timings = Timings()
    timings.reused("detection", "frozen S1 reused")
    timings.reused("grouping", "frozen S1 reused")
    timings.reused("association", "Goal 6 context diagnostics reused")
    timings.reused("cleaning", "Goal 6 E1-only cleaned pages reused")
    try:
        with timings.stage("input_load"):
            s1 = load_json(args.s1.resolve())
            if s1.get("status") != "completed" or s1.get("input_hashes_unchanged") is not True:
                raise ContractStop("S1 is not completed and hash-stable")
            assets = list(s1.get("assets", ()))
            if [item["asset_id"] for item in assets] != ["case-71", "case-72"]:
                raise ContractStop("unexpected frozen asset scope")
            input_lock = {
                "schema_version": "typesetting-input-contract-lock-v1",
                "created_at": utc_now(),
                "branch": git_value("branch", "--show-current"),
                "git_head": git_value("rev-parse", "--short", "HEAD"),
                "s1_sha256": sha256(args.s1.resolve()),
                "prompt_sha256": sha256(PROMPT_PATH),
                "repair_prompt_sha256": sha256(REPAIR_PROMPT_PATH),
                "font_sha256": sha256(args.font.resolve()),
                "sources": {item["asset_id"]: item["sha256"] for item in assets},
            }
            write_json(run_dir / "input-lock.json", input_lock)

        if args.reuse_upstream_dir:
            ocr_payload, translation_payload, ledger = import_checkpoint(
                args.reuse_upstream_dir.resolve(), run_dir, input_lock, timings,
            )
        else:
            with timings.stage("ocr_model_init"):
                ocr_runner = MangaOcrRunner()
            with timings.stage("ocr"):
                ocr_payload = run_ocr(ocr_runner, args.root.resolve(), assets, run_dir)
                write_json(run_dir / "ocr-results.json", ocr_payload)
            with timings.stage("translation"):
                translation_payload = translate_pages(ocr_payload, run_dir)
                write_json(run_dir / "translation-results.json", translation_payload)
            with timings.stage("provenance"):
                ledger = build_ledger(assets, ocr_payload, translation_payload, args.diagnostics_dir.resolve())
                write_json(run_dir / "provenance-ledger.json", ledger)
        with timings.stage("region_construction"):
            regions = construct_regions(args.root.resolve(), args.cleaned_dir.resolve(), assets, ledger, run_dir)
            write_json(run_dir / "region-candidates.json", public_regions(regions))
        with timings.stage("validator"):
            validator = run_validator(regions)
            if not validator["all_negative_cases_rejected"] or not validator["all_positive_cases_passed"]:
                raise ContractStop("validator grounding cases failed")
            write_json(run_dir / "validator-results.json", validator)
        with timings.stage("visualization"):
            visualize(assets, args.cleaned_dir.resolve(), ledger, regions, run_dir, args.font.resolve())
            write_form(ledger, run_dir)
        summary = {
            "schema_version": "typesetting-input-contract-summary-v1",
            "status": "READY_FOR_REGION_AND_MAPPING_REVIEW",
            "actual_translation_api_called": True,
            "translation_execution": "checkpoint" if args.reuse_upstream_dir else "current_attempt",
            "checkpoint_source": str(args.reuse_upstream_dir.resolve()) if args.reuse_upstream_dir else None,
            "page_count": 2,
            "fragment_coverage": ledger["completeness"]["coverage"],
            "segment_count": sum(len(item["blocks"]) for item in ledger["pages"]),
            "eligible_typesetting_block_count": sum(
                item["status"] == "eligible" for page in ledger["pages"] for item in page["blocks"]
            ),
            "excluded_block_count": sum(
                item["status"] == "excluded" for page in ledger["pages"] for item in page["blocks"]
            ),
            "validator": {
                "all_positive_cases_passed": validator["all_positive_cases_passed"],
                "all_negative_cases_rejected": validator["all_negative_cases_rejected"],
            },
            "gate": "PENDING_HUMAN_REGION_AND_MAPPING_REVIEW",
        }
        write_json(run_dir / "summary.json", summary)
        return run_dir
    finally:
        write_json(run_dir / "timings.json", timings.payload())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--s1", type=Path, required=True)
    parser.add_argument("--diagnostics-dir", type=Path, required=True)
    parser.add_argument("--cleaned-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--reuse-upstream-dir", type=Path)
    args = parser.parse_args()
    try:
        output = run(args)
    except (OSError, ValueError, json.JSONDecodeError, ContractStop, translation.SpikeStop) as error:
        print(f"STOP: {error}")
        return 2
    print(json.dumps({"status": "READY_FOR_REVIEW", "output_dir": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
