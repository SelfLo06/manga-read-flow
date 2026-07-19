from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import psutil
from PIL import Image, ImageDraw, ImageFont


MAX_ROI_PIXELS = 262_144
MAX_QUEUE_ENTRIES = 500_000
MAX_WORKING_MEMORY_MB = 511.0
MAX_ALGORITHM_SECONDS = 2.0
WORKER_WALL_TIMEOUT_SECONDS = 10.0

CONTENT_ROLES = {"ORDINARY_DIALOGUE", "CAPTION_LABEL", "SFX_DECORATIVE", "NOT_TEXT", "UNCERTAIN"}
EXPECTED_TASKS = {"COARSE_CONTAINER", "BOUNDED_SUPPORT", "LOCAL_SKIP", "UNCERTAIN"}
TOPOLOGIES = {"SAME", "DIFFERENT", "N_A", "UNCERTAIN"}

SELECTION = (
    ("G7-011", "ordinary_dialogue"),
    ("G7-014", "ordinary_dialogue"),
    ("G7-015", "ordinary_dialogue"),
    ("G7-018", "ordinary_dialogue"),
    ("G7-019", "ordinary_dialogue"),
    ("G7-020", "ordinary_dialogue"),
    ("G7-021", "ordinary_dialogue"),
    ("G7-023", "ordinary_dialogue"),
    ("G7-002", "touching_or_adjacent"),
    ("G7-005", "touching_or_adjacent"),
    ("G7-001", "negative_control"),
    ("G7-009", "negative_control"),
    ("G7-004", "uncertain_control"),
    ("G7-007", "uncertain_control"),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_form(content: str) -> dict[str, dict[str, str]]:
    headers = list(re.finditer(r"^## (G7-\d{3})\b.*$", content, flags=re.MULTILINE))
    labels: dict[str, dict[str, str]] = {}
    for index, header in enumerate(headers):
        review_id = header.group(1)
        end = headers[index + 1].start() if index + 1 < len(headers) else len(content)
        block = content[header.end() : end]

        def choice(field: str) -> str:
            match = re.search(rf"^- {re.escape(field)}:\s*`([^`]+)`", block, flags=re.MULTILINE)
            if not match:
                raise ValueError(f"Missing {field} for {review_id}")
            return match.group(1).strip()

        note_match = re.search(r"^- Note:\s*(.*)$", block, flags=re.MULTILINE)
        labels[review_id] = {
            "content_role": choice("ContentRole"),
            "expected_task": choice("ExpectedTask"),
            "topology": choice("Topology"),
            "phase_b": choice("PhaseB"),
            "note": note_match.group(1).strip() if note_match else "",
        }
    return labels


def parse_phase_b_form(content: str) -> dict[str, dict[str, str]]:
    headers = list(re.finditer(r"^## (G7-\d{3})\b.*$", content, flags=re.MULTILINE))
    labels: dict[str, dict[str, str]] = {}
    for index, header in enumerate(headers):
        review_id = header.group(1)
        end = headers[index + 1].start() if index + 1 < len(headers) else len(content)
        block = content[header.end() : end]

        def choice(field: str) -> str:
            match = re.search(rf"^- {re.escape(field)}:\s*`([^`]+)`", block, flags=re.MULTILINE)
            if not match:
                raise ValueError(f"Missing {field} for {review_id}")
            value = match.group(1).strip()
            if value == "未填":
                raise ValueError(f"Unfilled {field} for {review_id}")
            return value

        labels[review_id] = {
            "candidate_quality": choice("CandidateQuality"),
            "container_topology": choice("ContainerTopology"),
            "phase_c": choice("PhaseC"),
        }
    return labels


def evaluate_manual_gate(results: list[dict[str, Any]], labels: dict[str, dict[str, str]]) -> dict[str, Any]:
    valid_quality = {"CORRECT", "PARTIAL", "WRONG_OR_LEAK", "EMPTY", "EXPECTED_SKIP"}
    valid_topology = {"CORRECT", "WRONG", "N_A"}
    qualifying_categories = {"ordinary_dialogue", "touching_or_adjacent"}
    ordinary_groups = 0
    confirmed_groups = 0
    visible_groups = 0
    topology_wrong = 0
    expected_skip_errors = 0
    quality_counts: dict[str, int] = {}

    for result in results:
        review_id = result["review_id"]
        human = labels.get(review_id)
        if human is None:
            raise ValueError(f"Missing human review: {review_id}")
        quality = human["candidate_quality"]
        topology = human["container_topology"]
        phase_c = human["phase_c"]
        if quality not in valid_quality or topology not in valid_topology or phase_c not in {"YES", "NO"}:
            raise ValueError(f"Invalid human review values: {review_id}")
        quality_counts[quality] = quality_counts.get(quality, 0) + 1
        if not result["execute_b1"]:
            if quality != "EXPECTED_SKIP" or phase_c != "NO":
                expected_skip_errors += 1
            continue
        if result["category"] not in qualifying_categories:
            continue
        group_count = max(1, len(result.get("candidate_pixels", {})))
        ordinary_groups += group_count
        qualifying = quality in {"CORRECT", "PARTIAL"} and phase_c == "YES"
        if qualifying:
            confirmed_groups += group_count
            visible_groups += group_count
        if result["category"] == "touching_or_adjacent" and topology != "CORRECT":
            topology_wrong += 1

    rate = confirmed_groups / ordinary_groups if ordinary_groups else 0.0
    phase_c_authorized = (
        rate >= 0.80
        and visible_groups >= 8
        and topology_wrong == 0
        and expected_skip_errors == 0
    )
    return {
        "ordinary_dialogue_group_count": ordinary_groups,
        "confirmed_nonempty_group_count": confirmed_groups,
        "confirmed_nonempty_rate": rate,
        "visible_coarse_candidate_count": visible_groups,
        "topology_wrong_count": topology_wrong,
        "expected_skip_error_count": expected_skip_errors,
        "quality_counts": quality_counts,
        "phase_c_authorized": phase_c_authorized,
    }


def freeze_phase_b_review(form_path: Path, results_path: Path, output_path: Path) -> Path:
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite human review: {output_path}")
    result_payload = json.loads(results_path.read_text(encoding="utf-8"))
    labels = parse_phase_b_form(form_path.read_text(encoding="utf-8"))
    gate = evaluate_manual_gate(result_payload["results"], labels)
    automatic = result_payload["automatic_summary"]
    resource_pass = (
        automatic["worker_crash_count"] == 0
        and automatic["worker_timeout_count"] == 0
        and automatic["resource_abstention_count"] == 0
        and automatic["peak_rss_mb"] < 512.0
        and automatic["p95_algorithm_seconds"] < MAX_ALGORITHM_SECONDS
    )
    payload = {
        "schema_version": "goal7-phase-b-human-review-v1",
        "status": "FROZEN",
        "source_hashes": {"form": _sha256(form_path), "phase_b_results": _sha256(results_path)},
        "human_labels": labels,
        "gate": {
            **gate,
            "resource_pass": resource_pass,
            "false_low_risk_count": 0,
            "phase_c_authorized": gate["phase_c_authorized"] and resource_pass,
        },
        "verdict": "PASS_TO_PHASE_C" if gate["phase_c_authorized"] and resource_pass else "STOP_BEFORE_PHASE_C",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def l1_shape(width: int, height: int, max_pixels: int = MAX_ROI_PIXELS) -> tuple[tuple[int, int], float]:
    source_pixels = max(1, width * height)
    scale = min(1.0, math.sqrt(max_pixels / source_pixels))
    l1_width = max(1, math.floor(width * scale))
    l1_height = max(1, math.floor(height * scale))
    return (l1_height, l1_width), scale


def build_markers(shape: tuple[int, int], groups: list[dict[str, Any]]) -> tuple[np.ndarray, dict[str, int]]:
    height, width = shape
    markers = np.zeros((height, width), dtype=np.int32)
    markers[0, :] = 1
    markers[-1, :] = 1
    markers[:, 0] = 1
    markers[:, -1] = 1
    labels: dict[str, int] = {}
    for label, group in enumerate(groups, start=2):
        labels[group["group_id"]] = label
        for x, y, box_width, box_height in group["fragment_boxes"]:
            x1 = max(1, min(width - 1, int(x)))
            y1 = max(1, min(height - 1, int(y)))
            x2 = max(x1 + 1, min(width - 1, int(x + box_width)))
            y2 = max(y1 + 1, min(height - 1, int(y + box_height)))
            inset_x = max(1, (x2 - x1) // 5)
            inset_y = max(1, (y2 - y1) // 5)
            sx1, sx2 = x1 + inset_x, max(x1 + inset_x + 1, x2 - inset_x)
            sy1, sy2 = y1 + inset_y, max(y1 + inset_y + 1, y2 - inset_y)
            markers[sy1:sy2, sx1:sx2] = label
    return markers, labels


def run_local_watershed(image: np.ndarray, groups: list[dict[str, Any]]) -> dict[str, Any]:
    from skimage.segmentation import watershed

    markers, group_labels = build_markers(image.shape[:2], groups)
    gray = (
        image[..., 0].astype(np.float32) * 0.299
        + image[..., 1].astype(np.float32) * 0.587
        + image[..., 2].astype(np.float32) * 0.114
    ) / 255.0
    gradient_y, gradient_x = np.gradient(gray)
    gradient = np.hypot(gradient_x, gradient_y).astype(np.float32)
    labels = watershed(gradient, markers=markers, watershed_line=True).astype(np.int32)
    return {
        "labels": labels,
        "virtual_boundary": np.logical_and(labels == 0, markers == 0),
        "group_labels": group_labels,
    }


def freeze_selection(form_path: Path, index_path: Path, matrix_path: Path, output_path: Path) -> Path:
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite selection: {output_path}")
    labels = parse_form(form_path.read_text(encoding="utf-8"))
    index = json.loads(index_path.read_text(encoding="utf-8"))
    by_id = {item["review_id"]: item for item in index["items"]}
    items: list[dict[str, Any]] = []
    for review_id, category in SELECTION:
        if review_id not in labels or review_id not in by_id:
            raise ValueError(f"Selection item missing: {review_id}")
        human = labels[review_id]
        if human["content_role"] not in CONTENT_ROLES:
            raise ValueError(f"Invalid ContentRole for {review_id}")
        if human["expected_task"] not in EXPECTED_TASKS:
            raise ValueError(f"Invalid ExpectedTask for {review_id}")
        if human["topology"] not in TOPOLOGIES:
            raise ValueError(f"Invalid Topology for {review_id}")
        if human["phase_b"] not in {"YES", "NO"}:
            raise ValueError(f"Invalid PhaseB for {review_id}")
        execute_b1 = category in {"ordinary_dialogue", "touching_or_adjacent"}
        if execute_b1 and not (
            human["content_role"] == "ORDINARY_DIALOGUE"
            and human["expected_task"] == "COARSE_CONTAINER"
            and human["phase_b"] == "YES"
        ):
            raise ValueError(f"Positive Phase B item contradicts human labels: {review_id}")
        if not execute_b1 and human["phase_b"] != "NO":
            raise ValueError(f"Control must remain excluded from B1: {review_id}")
        items.append(
            {
                "review_id": review_id,
                "category": category,
                "execute_b1": execute_b1,
                "human_labels": human,
                "cluster": {key: value for key, value in by_id[review_id].items() if key not in {"image"}},
            }
        )
    payload = {
        "schema_version": "goal7-phase-b-selection-v1",
        "status": "FROZEN",
        "source_hashes": {
            "form": _sha256(form_path),
            "index": _sha256(index_path),
            "phase_a_matrix": _sha256(matrix_path),
        },
        "resource_contract": {
            "max_roi_pixels": MAX_ROI_PIXELS,
            "max_queue_entries": MAX_QUEUE_ENTRIES,
            "max_working_memory_mb": MAX_WORKING_MEMORY_MB,
            "max_algorithm_seconds": MAX_ALGORITHM_SECONDS,
            "worker_wall_timeout_seconds": WORKER_WALL_TIMEOUT_SECONDS,
        },
        "counts": {
            "ordinary_dialogue": 8,
            "touching_or_adjacent": 2,
            "negative_control": 2,
            "uncertain_control": 2,
            "b1_execution": 10,
            "local_skip": 4,
        },
        "items": items,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def _bbox(raw: dict[str, Any]) -> tuple[int, int, int, int]:
    return int(raw["x"]), int(raw["y"]), int(raw["width"]), int(raw["height"])


def _prepare_request(item: dict[str, Any], asset: dict[str, Any], source: Path) -> dict[str, Any]:
    cluster = item["cluster"]
    group_ids = set(cluster["group_ids"])
    fragments = {fragment["fragment_id"]: fragment for fragment in asset["fragments"]}
    groups: list[dict[str, Any]] = []
    for group in asset["groups"]:
        if group["group_id"] not in group_ids:
            continue
        groups.append(
            {
                "group_id": group["group_id"],
                "fragment_boxes": [
                    list(_bbox(fragments[fragment_id]["bbox"]))
                    for fragment_id in group["ordered_fragment_ids"]
                    if fragment_id in fragments
                ],
            }
        )
    return {
        "review_id": item["review_id"],
        "page_id": cluster["page_id"],
        "cluster_id": cluster["cluster_id"],
        "category": item["category"],
        "execute_b1": item["execute_b1"],
        "human_labels": item["human_labels"],
        "source": str(source),
        "local_roi": cluster["local_roi"],
        "groups": groups,
        "resource_contract": {
            "max_roi_pixels": MAX_ROI_PIXELS,
            "max_queue_entries": MAX_QUEUE_ENTRIES,
            "max_working_memory_mb": MAX_WORKING_MEMORY_MB,
            "max_algorithm_seconds": MAX_ALGORITHM_SECONDS,
        },
    }


def _seed_overlay(crop: Image.Image, groups: list[dict[str, Any]], roi: tuple[int, int, int, int]) -> Image.Image:
    result = crop.convert("RGB")
    draw = ImageDraw.Draw(result)
    colors = ((255, 40, 40), (20, 90, 255), (255, 160, 0), (180, 0, 220))
    roi_x, roi_y, _, _ = roi
    for index, group in enumerate(groups):
        color = colors[index % len(colors)]
        for x, y, width, height in group["fragment_boxes"]:
            draw.rectangle((x - roi_x, y - roi_y, x + width - roi_x, y + height - roi_y), outline=color, width=3)
    return result


def _coarse_overlay(crop: Image.Image, labels: np.ndarray, group_labels: dict[str, int], boundary: np.ndarray) -> Image.Image:
    base = np.asarray(crop.convert("RGB"), dtype=np.float32)
    colors = ((40, 220, 120), (40, 130, 255), (255, 170, 30), (220, 50, 220))
    for index, label in enumerate(group_labels.values()):
        mask = labels == label
        color = np.asarray(colors[index % len(colors)], dtype=np.float32)
        base[mask] = base[mask] * 0.55 + color * 0.45
    base[boundary] = np.asarray((255, 30, 30), dtype=np.float32)
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")


def run_worker(request_path: Path, output_dir: Path) -> Path:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=False)
    roi = _bbox(request["local_roi"])
    roi_x, roi_y, roi_width, roi_height = roi
    with Image.open(request["source"]) as source:
        crop = source.crop((roi_x, roi_y, roi_x + roi_width, roi_y + roi_height)).convert("RGB")
    crop.save(output_dir / "source.png")
    _seed_overlay(crop, request["groups"], roi).save(output_dir / "seed-overlay.png")

    result: dict[str, Any] = {
        "review_id": request["review_id"],
        "page_id": request["page_id"],
        "cluster_id": request["cluster_id"],
        "category": request["category"],
        "execute_b1": request["execute_b1"],
        "human_labels": request["human_labels"],
        "source_roi": request["local_roi"],
    }
    if not request["execute_b1"]:
        skipped = crop.copy()
        draw = ImageDraw.Draw(skipped)
        draw.rectangle((0, 0, skipped.width - 1, skipped.height - 1), outline=(255, 170, 0), width=5)
        draw.text((12, 12), "LOCAL SKIP (human-frozen control)", fill=(255, 50, 0))
        skipped.save(output_dir / "b1-coarse-overlay.png")
        result.update(
            {
                "status": "EXPECTED_LOCAL_SKIP",
                "algorithm_seconds": 0.0,
                "l1_shape": None,
                "l1_scale": None,
                "estimated_queue_entries": 0,
                "candidate_count": 0,
                "nonempty_candidate": False,
                "virtual_boundary_pixels": 0,
            }
        )
    else:
        (l1_height, l1_width), scale = l1_shape(crop.width, crop.height, MAX_ROI_PIXELS)
        l1 = crop.resize((l1_width, l1_height), Image.Resampling.LANCZOS)
        scaled_groups: list[dict[str, Any]] = []
        for group in request["groups"]:
            scaled_groups.append(
                {
                    "group_id": group["group_id"],
                    "fragment_boxes": [
                        (
                            round((x - roi_x) * scale),
                            round((y - roi_y) * scale),
                            max(1, round(width * scale)),
                            max(1, round(height * scale)),
                        )
                        for x, y, width, height in group["fragment_boxes"]
                    ],
                }
            )
        if l1_width * l1_height > MAX_QUEUE_ENTRIES:
            raise RuntimeError("L1 working domain exceeds queue budget")
        started = time.perf_counter()
        watershed_result = run_local_watershed(np.asarray(l1), scaled_groups)
        algorithm_seconds = time.perf_counter() - started
        label_image = Image.fromarray(watershed_result["labels"].astype(np.int32), mode="I")
        labels_full = np.asarray(label_image.resize(crop.size, Image.Resampling.NEAREST), dtype=np.int32)
        boundary_image = Image.fromarray(watershed_result["virtual_boundary"].astype(np.uint8) * 255, mode="L")
        boundary_full = np.asarray(boundary_image.resize(crop.size, Image.Resampling.NEAREST)) > 0
        _coarse_overlay(crop, labels_full, watershed_result["group_labels"], boundary_full).save(
            output_dir / "b1-coarse-overlay.png"
        )
        candidate_pixels = {
            group_id: int(np.count_nonzero(labels_full == label))
            for group_id, label in watershed_result["group_labels"].items()
        }
        result.update(
            {
                "status": "B1_COMPLETED",
                "algorithm_seconds": algorithm_seconds,
                "l1_shape": [l1_height, l1_width],
                "l1_scale": scale,
                "estimated_queue_entries": l1_width * l1_height,
                "candidate_count": len(candidate_pixels),
                "candidate_pixels": candidate_pixels,
                "nonempty_candidate": bool(candidate_pixels) and all(value > 0 for value in candidate_pixels.values()),
                "virtual_boundary_pixels": int(np.count_nonzero(boundary_full)),
            }
        )
    result_path = output_dir / "result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result_path


def _monitor_worker(command: list[str], cwd: Path) -> tuple[int, float, float, str, str]:
    started = time.perf_counter()
    process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    ps_process = psutil.Process(process.pid)
    peak_rss = 0
    timed_out = False
    while process.poll() is None:
        try:
            processes = [ps_process, *ps_process.children(recursive=True)]
            peak_rss = max(peak_rss, sum(item.memory_info().rss for item in processes if item.is_running()))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        if time.perf_counter() - started > WORKER_WALL_TIMEOUT_SECONDS:
            timed_out = True
            process.kill()
            break
        time.sleep(0.01)
    stdout, stderr = process.communicate()
    wall_seconds = time.perf_counter() - started
    return (124 if timed_out else int(process.returncode), wall_seconds, peak_rss / (1024 * 1024), stdout, stderr)


def _fit_thumbnail(path: Path, width: int = 400, height: int = 280) -> Image.Image:
    with Image.open(path) as image:
        copy = image.convert("RGB")
    copy.thumbnail((width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height), "white")
    canvas.paste(copy, ((width - copy.width) // 2, (height - copy.height) // 2))
    return canvas


def _write_contact_sheet(results: list[dict[str, Any]], output_dir: Path) -> None:
    tile_width, tile_height = 420, 340
    sheet = Image.new("RGB", (tile_width * 3, tile_height * len(results)), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=16)
    for row, result in enumerate(results):
        case_dir = output_dir / "cases" / result["review_id"]
        paths = (case_dir / "source.png", case_dir / "seed-overlay.png", case_dir / "b1-coarse-overlay.png")
        for column, path in enumerate(paths):
            sheet.paste(_fit_thumbnail(path), (column * tile_width + 10, row * tile_height + 50))
        title = (
            f'{result["review_id"]} | {result["page_id"]} | {result["status"]} | '
            f'B1={result["execute_b1"]} | {result.get("algorithm_seconds", 0.0):.3f}s | '
            f'{result.get("peak_rss_mb", 0.0):.1f}MB'
        )
        draw.text((10, row * tile_height + 8), title, fill="black", font=font)
        draw.text((10, row * tile_height + 29), "SOURCE", fill="black", font=font)
        draw.text((tile_width + 10, row * tile_height + 29), "SEEDS", fill="black", font=font)
        draw.text((tile_width * 2 + 10, row * tile_height + 29), "B1 COARSE / SKIP", fill="black", font=font)
    sheet.save(output_dir / "CONTACT-SHEET.png")


def _write_form(results: list[dict[str, Any]], output_dir: Path) -> None:
    lines = [
        "# Goal 7 Phase B 可见结果审查",
        "",
        "第三列绿色/蓝色区域是 coarse association，不是 Pixel Text Mask，也没有执行 Cleaning。红线是多源竞争边界候选。",
        "",
        "每项请选择：",
        "",
        "- `CandidateQuality`: `CORRECT` / `PARTIAL` / `WRONG_OR_LEAK` / `EMPTY` / `EXPECTED_SKIP`",
        "- `ContainerTopology`: `CORRECT` / `WRONG` / `N_A`",
        "- `PhaseC`: `YES` / `NO`",
        "",
    ]
    for result in results:
        review_id = result["review_id"]
        if not result["execute_b1"]:
            quality_default = "EXPECTED_SKIP"
            topology_default = "N_A"
            phase_c_default = "NO"
        elif result["category"] == "ordinary_dialogue":
            quality_default = "未填"
            topology_default = "N_A"
            phase_c_default = "未填"
        else:
            quality_default = "未填"
            topology_default = "未填"
            phase_c_default = "未填"
        lines.extend(
            [
                f"## {review_id} — {result['page_id']} / {result['category']}",
                "",
                f"![{review_id}](cases/{review_id}/b1-coarse-overlay.png)",
                "",
                f"- Execution: `{result['status']}`",
                f"- CandidateQuality: `{quality_default}`",
                f"- ContainerTopology: `{topology_default}`",
                f"- PhaseC: `{phase_c_default}`",
                "- Note: ",
                "",
            ]
        )
    (output_dir / "FORM.md").write_text("\n".join(lines), encoding="utf-8")


def run_phase_b(selection_path: Path, s1_results_path: Path, root: Path, output_dir: Path) -> Path:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite Phase B output: {output_dir}")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    s1 = json.loads(s1_results_path.read_text(encoding="utf-8"))
    if s1.get("status") != "completed" or not s1.get("input_hashes_unchanged"):
        raise RuntimeError("S1 is not frozen and unchanged")
    assets = {asset["asset_id"]: asset for asset in s1["assets"]}
    output_dir.mkdir(parents=True)
    requests_dir = output_dir / "requests"
    requests_dir.mkdir()
    cases_dir = output_dir / "cases"
    cases_dir.mkdir()
    results: list[dict[str, Any]] = []
    cwd = Path(__file__).resolve().parents[3]

    for item in selection["items"]:
        page_id = item["cluster"]["page_id"]
        asset = assets[page_id]
        source = root / asset["relative_path"]
        if _sha256(source) != asset["sha256"]:
            raise RuntimeError(f"Frozen source changed: {page_id}")
        request = _prepare_request(item, asset, source)
        request_path = requests_dir / f'{item["review_id"]}.json'
        request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        case_dir = cases_dir / item["review_id"]
        command = [
            sys.executable,
            "-m",
            "tools.experiments.grouping_120.text_seeded_container_association.goal7_phase_b",
            "worker",
            "--request",
            str(request_path),
            "--output-dir",
            str(case_dir),
        ]
        returncode, wall_seconds, peak_rss_mb, stdout, stderr = _monitor_worker(command, cwd)
        if returncode != 0:
            results.append(
                {
                    "review_id": item["review_id"],
                    "page_id": page_id,
                    "category": item["category"],
                    "execute_b1": item["execute_b1"],
                    "status": "WORKER_TIMEOUT" if returncode == 124 else "WORKER_CRASH",
                    "returncode": returncode,
                    "wall_seconds": wall_seconds,
                    "peak_rss_mb": peak_rss_mb,
                    "stderr": stderr[-2000:],
                    "stdout": stdout[-2000:],
                }
            )
            continue
        result_path = case_dir / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result.update({"wall_seconds": wall_seconds, "peak_rss_mb": peak_rss_mb, "worker_returncode": returncode})
        if result["execute_b1"] and (
            result["algorithm_seconds"] >= MAX_ALGORITHM_SECONDS or peak_rss_mb >= 512.0
        ):
            result["status"] = "RESOURCE_ABSTENTION"
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append(result)

    b1_results = [item for item in results if item["execute_b1"]]
    algorithm_times = sorted(item.get("algorithm_seconds", math.inf) for item in b1_results)
    p95_index = max(0, math.ceil(len(algorithm_times) * 0.95) - 1)
    summary = {
        "schema_version": "goal7-phase-b-results-v1",
        "status": "AWAITING_HUMAN_VISUAL_REVIEW",
        "source_hashes": {
            "selection": _sha256(selection_path),
            "s1_results": _sha256(s1_results_path),
        },
        "contract": {
            "detection_rerun": False,
            "pixel_text_mask": False,
            "cleaning": False,
            "max_roi_pixels": MAX_ROI_PIXELS,
            "max_queue_entries": MAX_QUEUE_ENTRIES,
            "max_working_memory_mb": MAX_WORKING_MEMORY_MB,
            "max_algorithm_seconds": MAX_ALGORITHM_SECONDS,
        },
        "automatic_summary": {
            "case_count": len(results),
            "b1_execution_count": len(b1_results),
            "expected_local_skip_count": sum(item["status"] == "EXPECTED_LOCAL_SKIP" for item in results),
            "nonempty_b1_count": sum(item.get("nonempty_candidate", False) for item in b1_results),
            "worker_crash_count": sum(item["status"] == "WORKER_CRASH" for item in results),
            "worker_timeout_count": sum(item["status"] == "WORKER_TIMEOUT" for item in results),
            "resource_abstention_count": sum(item["status"] == "RESOURCE_ABSTENTION" for item in results),
            "peak_rss_mb": max((item.get("peak_rss_mb", 0.0) for item in results), default=0.0),
            "p95_algorithm_seconds": algorithm_times[p95_index] if algorithm_times else 0.0,
        },
        "results": results,
    }
    results_path = output_dir / "PHASE-B-RESULTS.json"
    results_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if all((cases_dir / item["review_id"] / "b1-coarse-overlay.png").exists() for item in results):
        _write_contact_sheet(results, output_dir)
        _write_form(results, output_dir)
    return results_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Goal 7 bounded local B1 Phase B")
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--form", type=Path, required=True)
    freeze.add_argument("--index", type=Path, required=True)
    freeze.add_argument("--matrix", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    review = commands.add_parser("freeze-review")
    review.add_argument("--form", type=Path, required=True)
    review.add_argument("--results", type=Path, required=True)
    review.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--selection", type=Path, required=True)
    run.add_argument("--s1-results", type=Path, required=True)
    run.add_argument("--root", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    worker = commands.add_parser("worker")
    worker.add_argument("--request", type=Path, required=True)
    worker.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "freeze":
        print(freeze_selection(args.form, args.index, args.matrix, args.output))
    elif args.command == "freeze-review":
        print(freeze_phase_b_review(args.form, args.results, args.output))
    elif args.command == "run":
        print(run_phase_b(args.selection, args.s1_results, args.root, args.output_dir))
    elif args.command == "worker":
        print(run_worker(args.request, args.output_dir))


if __name__ == "__main__":
    main()
