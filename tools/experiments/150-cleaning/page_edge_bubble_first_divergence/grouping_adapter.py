"""Oracle-free bridge to the existing text-region Grouping spike.

The reused spike groups Detection fragments into text groups from their
geometry.  It does not infer a speech-bubble/container, and this adapter keeps
that limitation explicit rather than inventing a BubbleInstance assignment.
"""
from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[4]
GROUPING_SPIKE = ROOT / "tools/experiments/120-grouping/text_region_grouping/spike.py"


class GroupingAdapterError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_grouping_spike() -> Any:
    if not GROUPING_SPIKE.is_file():
        raise GroupingAdapterError(f"existing Grouping spike is missing: {GROUPING_SPIKE}")
    spec = importlib.util.spec_from_file_location("page_edge_existing_text_region_grouping", GROUPING_SPIKE)
    if spec is None or spec.loader is None:
        raise GroupingAdapterError("cannot load existing Grouping spike")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _integer_bbox(value: dict[str, Any], *, width: int, height: int) -> dict[str, int]:
    try:
        bbox = {name: float(value[name]) for name in ("x", "y", "width", "height")}
    except (KeyError, TypeError, ValueError) as error:
        raise GroupingAdapterError("Detection candidate lacks numeric bbox_full_page") from error
    if any(number != int(number) for number in bbox.values()):
        raise GroupingAdapterError(f"existing grouping spike requires integer bbox coordinates: {value}")
    normalized = {name: int(number) for name, number in bbox.items()}
    if not (0 <= normalized["x"] < normalized["x"] + normalized["width"] <= width and 0 <= normalized["y"] < normalized["y"] + normalized["height"] <= height):
        raise GroupingAdapterError(f"Detection candidate bbox is out of full-page bounds: {value}")
    return normalized


def _color(index: int) -> tuple[int, int, int]:
    palette = ((230, 57, 70), (29, 161, 242), (46, 204, 113), (241, 196, 15), (155, 89, 182), (230, 126, 34), (26, 188, 156))
    return palette[(index - 1) % len(palette)]


def run(*, asset_id: str, source_path: Path, source_sha256: str, detection_candidates_path: Path, detection_candidates_sha256: str, output_dir: Path) -> dict[str, Any]:
    """Group frozen full-page Detection candidates without inspecting oracle data."""
    if not isinstance(asset_id, str) or not asset_id:
        raise GroupingAdapterError("asset_id must be a non-empty string")
    if not source_path.is_file() or sha256_file(source_path) != source_sha256:
        raise GroupingAdapterError("source hash mismatch")
    if not detection_candidates_path.is_file() or sha256_file(detection_candidates_path) != detection_candidates_sha256:
        raise GroupingAdapterError("Detection candidates artifact hash mismatch")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise GroupingAdapterError(f"grouping output directory is not empty: {output_dir}")
    try:
        candidates_doc = json.loads(detection_candidates_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise GroupingAdapterError("invalid Detection candidates JSON") from error
    if candidates_doc.get("source_sha256") != source_sha256 or candidates_doc.get("coordinate_space") != "full_page":
        raise GroupingAdapterError("Detection candidates do not bind to the full-page source")
    dimensions = candidates_doc.get("image_dimensions") or {}
    with Image.open(source_path) as image:
        source_width, source_height = image.size
    if dimensions != {"width": source_width, "height": source_height}:
        raise GroupingAdapterError("Detection candidate dimensions do not match source")
    candidates = candidates_doc.get("candidates")
    if not isinstance(candidates, list):
        raise GroupingAdapterError("Detection candidates must be a list")
    output_dir.mkdir(parents=True, exist_ok=True)
    grouping = _load_grouping_spike()
    fragments = []
    seen: set[str] = set()
    for candidate in candidates:
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id or candidate_id in seen:
            raise GroupingAdapterError("Detection candidate IDs must be unique non-empty strings")
        seen.add(candidate_id)
        polygon = candidate.get("geometry")
        if candidate.get("geometry_type") != "polygon" or not isinstance(polygon, list):
            raise GroupingAdapterError(f"candidate {candidate_id} lacks a polygon geometry")
        fragments.append(
            grouping.FragmentInput(
                fragment_id=candidate_id,
                asset_id=asset_id,
                bbox=_integer_bbox(candidate.get("bbox_full_page") or {}, width=source_width, height=source_height),
                polygon=polygon,
                score=candidate.get("confidence"),
                ocr_text="",
                ocr_error=None,
            )
        )
    try:
        groups = grouping.group_fragments(
            grouping.PageGroupingInput(asset_id=asset_id, width=source_width, height=source_height, fragments=fragments)
        )
    except Exception as error:  # pragma: no cover - reused implementation failure is runtime evidence
        raise GroupingAdapterError(f"existing Grouping spike failed: {error!r}") from error
    serialized_groups = [grouping.to_jsonable_group(group) for group in groups]
    group_by_candidate = {
        candidate_id: group["group_id"]
        for group in serialized_groups
        for candidate_id in group["ordered_fragment_ids"]
    }
    assignments = [
        {
            "candidate_id": candidate["candidate_id"],
            "text_group_id": group_by_candidate[candidate["candidate_id"]],
            "bubble_instance_id": None,
            "container_assignment_status": "NOT_AVAILABLE",
            "container_assignment_reason": "geometry-only text-region grouping spike does not infer BubbleInstance/container",
        }
        for candidate in candidates
    ]
    config = {
        "implementation": "tools/experiments/120-grouping/text_region_grouping/spike.py:group_fragments",
        "algorithm_input": "frozen_full_page_detection_candidates",
        "orientation_ratio": grouping.ORIENTATION_RATIO,
        "projection_overlap_ratio": grouping.PROJECTION_OVERLAP_RATIO,
        "gap_relative_limit": grouping.GAP_RELATIVE_LIMIT,
        "gap_min_px": grouping.GAP_MIN_PX,
    }
    provenance = {
        "implementation": config["implementation"],
        "adapter_sha256": sha256_file(Path(__file__)),
        "grouping_spike_sha256": sha256_file(GROUPING_SPIKE),
        "source_sha256": source_sha256,
        "detection_candidates_sha256": detection_candidates_sha256,
        "coordinate_space": "full_page",
        "container_assignment": "not_produced_by_reused_text-region grouping spike",
    }
    document = {
        "schema_version": "page-edge-bubble-grouping-assignments-v1",
        "source_sha256": source_sha256,
        "detection_candidates_sha256": detection_candidates_sha256,
        "coordinate_space": "full_page",
        "candidate_count": len(candidates),
        "automatic_text_group_count": len(serialized_groups),
        "groups": serialized_groups,
        "candidate_assignments": assignments,
    }
    _write_json(output_dir / "grouping_assignments.json", document)
    _write_json(output_dir / "grouping_config.json", config)
    _write_json(output_dir / "grouping_provenance.json", provenance)
    with Image.open(source_path) as image:
        overlay = image.convert("RGB")
    draw = ImageDraw.Draw(overlay)
    for index, group in enumerate(serialized_groups, start=1):
        box = group["bbox"]
        color = _color(index)
        draw.rectangle((box["x"], box["y"], box["x"] + box["width"], box["y"] + box["height"]), outline=color, width=4)
        draw.text((box["x"] + 2, box["y"] + 2), group["group_id"], fill=color)
    overlay.save(output_dir / "grouping_overlay.png", "PNG")
    return {
        "candidate_count": len(candidates),
        "automatic_text_group_count": len(serialized_groups),
        "assignments_path": output_dir / "grouping_assignments.json",
        "config_path": output_dir / "grouping_config.json",
        "provenance_path": output_dir / "grouping_provenance.json",
        "overlay_path": output_dir / "grouping_overlay.png",
        "implementation": config["implementation"],
    }
