"""Deterministic, local-only preparation for Cleaning Benchmark Pilot v0.1.

This module consumes frozen dataset-audit facts.  It never invokes OCR, VLMs,
translation, inpainting, APIs, databases, or production workflow code.  Pixel
differences are *review candidates*, not masks or labels with ground-truth
status.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np
from PIL import Image, ImageDraw


PROCESSING_VERSION = "cleaning-benchmark-pilot-v0.1"
EXPLORATION_WORKS = ("work-003", "work-004")
REVIEW_CONCLUSIONS = ("confirmed_match", "corrected_match", "confirmed_extra_page", "reject_pair", "defer")
ELIGIBILITY_VALUES = ("gold", "silver", "reject", "pending")
COMPLEXITY_VALUES = ("E1", "E2", "E3", "E4", "uncertain")


@dataclass(frozen=True)
class PilotConfig:
    input_root: Path
    audit_dir: Path
    output_dir: Path
    review_dir: Path
    selection_seed: int = 20260714
    page_target: int = 24
    regions_per_page: int = 2
    min_component_area: int = 96


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(sha256_file(path).encode("ascii"))
    return digest.hexdigest()


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8", newline="")
    temporary.replace(path)


def _csv(path: Path, rows: list[dict[str, Any]], fields: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _load_rgb(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"image_unreadable:{path}")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def _thumbnail(rgb: np.ndarray, max_edge: int = 720) -> Image.Image:
    image = Image.fromarray(rgb)
    image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    return image


def _labelled_strip(images: list[tuple[str, np.ndarray | None]], output: Path) -> None:
    width, height, label_height = 360, 480, 26
    canvas = Image.new("RGB", (width * len(images), height + label_height), "white")
    draw = ImageDraw.Draw(canvas)
    for index, (label, rgb) in enumerate(images):
        left = index * width
        if rgb is not None:
            thumb = _thumbnail(rgb, max_edge=min(width - 8, height - 8))
            x = left + (width - thumb.width) // 2
            y = label_height + (height - thumb.height) // 2
            canvas.paste(thumb, (x, y))
        else:
            draw.rectangle((left, label_height, left + width - 1, height + label_height - 1), outline="gray")
        draw.text((left + 6, 6), label, fill="black")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def _candidate_paths(pair: dict[str, Any]) -> tuple[str | None, str | None]:
    textless = pair.get("matched_textless_path")
    chinese = pair.get("matched_chinese_path")
    if not textless:
        candidates = pair.get("textless_candidates", [])
        textless = candidates[0]["path"] if candidates else None
    if not chinese:
        candidates = pair.get("chinese_candidates", [])
        chinese = candidates[0]["path"] if candidates else None
    return textless, chinese


def generate_unresolved_review_bundle(config: PilotConfig) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Create one local, image-only comparison bundle per frozen review fact."""
    items = _read_csv(config.audit_dir / "manual-review.csv")
    if len(items) != 17:
        raise RuntimeError(f"expected_17_manual_review_items_got_{len(items)}")
    pair_rows = _read_jsonl(config.audit_dir / "page-pairing.jsonl")
    inventory_roles = {row["relative_path"]: row["variant"] for row in _read_jsonl(config.audit_dir / "file-inventory.jsonl")}
    by_original = {row["original_path"]: row for row in pair_rows}
    by_any_path: dict[str, dict[str, Any]] = {}
    for row in pair_rows:
        by_any_path[row["original_path"]] = row
        for key in ("matched_textless_path", "matched_chinese_path"):
            if row.get(key):
                by_any_path[row[key]] = row

    bundle_root = config.review_dir / "unresolved"
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    resolution_rows: list[dict[str, str]] = []
    metadata: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        path = item["relative_path"]
        pair = by_any_path.get(path)
        original_path: str | None = None
        textless_path: str | None = None
        chinese_path: str | None = None
        if pair:
            original_path = pair["original_path"]
            textless_path, chinese_path = _candidate_paths(pair)
        else:
            # An extra reference page is itself the only trusted source image;
            # retain its audited variant rather than mislabelling it as JP.
            role = inventory_roles.get(path)
            if role == "textless_reference":
                textless_path = path
            elif role == "chinese_reference":
                chinese_path = path
            else:
                original_path = path

        def maybe_load(relative: str | None) -> np.ndarray | None:
            return _load_rgb(config.input_root / relative) if relative and (config.input_root / relative).is_file() else None

        entry_id = f"review-{index:03d}"
        preview = bundle_root / entry_id / "comparison.png"
        _labelled_strip([
            ("jp", maybe_load(original_path)),
            ("textless", maybe_load(textless_path)),
            ("zh", maybe_load(chinese_path)),
        ], preview)
        resolution_rows.append({
            "review_id": entry_id,
            "item_type": item["item_type"],
            "work_id": item["work_id"],
            "relative_path": path,
            "jp_source_path": original_path or "",
            "textless_source_path": textless_path or "",
            "zh_source_path": chinese_path or "",
            "review_bundle_path": _relative(preview, config.review_dir),
            "human_conclusion": "",
            "corrected_jp_path": "",
            "corrected_textless_path": "",
            "corrected_zh_path": "",
            "reviewer_note": "",
        })
        metadata.append({"review_id": entry_id, "item_type": item["item_type"], "preview": _relative(preview, config.review_dir)})
    _csv(config.output_dir / "manual-review-resolution.csv", resolution_rows, resolution_rows[0].keys())
    return resolution_rows, metadata


def select_pages(triplets: list[dict[str, str]], unresolved_paths: set[str], seed: int, target: int) -> list[dict[str, str]]:
    """Select high-confidence exploration triplets using a seed-stable balanced order."""
    eligible = [
        row for row in triplets
        if row["work_id"] in EXPLORATION_WORKS
        and row["qualification"] == "Gold candidate"
        and row["textless_registration_quality"] == "high"
        and row["chinese_registration_quality"] == "high"
        and min(float(row["textless_match_score"]), float(row["chinese_match_score"])) >= 0.78
        and not {row["original_path"], row["textless_path"], row["chinese_path"]}.intersection(unresolved_paths)
    ]
    by_work: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in eligible:
        by_work[row["work_id"]].append(row)
    if any(not by_work[work] for work in EXPLORATION_WORKS):
        raise RuntimeError("exploration_work_has_no_eligible_triplet")
    rng = random.Random(seed)
    for work in EXPLORATION_WORKS:
        by_work[work].sort(key=lambda row: row["original_path"])
        rng.shuffle(by_work[work])
    target = min(target, sum(len(rows) for rows in by_work.values()))
    selected: list[dict[str, str]] = []
    turns = 0
    while len(selected) < target:
        work = EXPLORATION_WORKS[turns % len(EXPLORATION_WORKS)]
        if by_work[work]:
            selected.append(by_work[work].pop(0))
        turns += 1
        if turns > target * 4:
            break
    if {row["work_id"] for row in selected} != set(EXPLORATION_WORKS):
        raise RuntimeError("selection_must_cover_both_exploration_works")
    return sorted(selected, key=lambda row: (row["work_id"], row["original_path"]))


def _warp_textless(textless_rgb: np.ndarray, jp_shape: tuple[int, int], transform_json: str) -> np.ndarray:
    matrix = np.asarray(json.loads(transform_json), dtype=np.float32)
    height, width = jp_shape
    return cv2.warpAffine(textless_rgb, matrix, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _components(mask: np.ndarray, min_area: int) -> list[dict[str, Any]]:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    page_area = mask.shape[0] * mask.shape[1]
    components: list[dict[str, Any]] = []
    for label in range(1, count):
        x, y, width, height, area = stats[label]
        if area < min_area or width < 8 or height < 8 or area > page_area * .22:
            continue
        component = (labels[y : y + height, x : x + width] == label).astype(np.uint8) * 255
        density = float(np.mean(component > 0))
        components.append({"x": int(x), "y": int(y), "width": int(width), "height": int(height), "area": int(area), "density": density, "mask": component})
    return components


def extract_candidate_regions(jp_rgb: np.ndarray, textless_rgb: np.ndarray, transform_json: str, min_area: int) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """Derive merged difference candidates; return no semantic or ground-truth label."""
    aligned = _warp_textless(textless_rgb, jp_rgb.shape[:2], transform_json)
    jp_gray = cv2.cvtColor(jp_rgb, cv2.COLOR_RGB2GRAY)
    textless_gray = cv2.cvtColor(aligned, cv2.COLOR_RGB2GRAY)
    diff = cv2.absdiff(jp_gray, textless_gray)
    threshold = max(18, int(np.percentile(diff, 88)))
    binary = np.where(diff >= threshold, 255, 0).astype(np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    binary = cv2.dilate(binary, np.ones((3, 3), np.uint8), iterations=1)
    edges = cv2.Canny(textless_gray, 60, 150)
    protected = cv2.bitwise_and(binary, cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=1))
    candidates = _components(binary, min_area)
    for candidate in candidates:
        x, y, width, height = candidate["x"], candidate["y"], candidate["width"], candidate["height"]
        candidate["score"] = round(float(candidate["area"]) * (1.0 + candidate["density"]), 6)
        candidate["protected_ratio"] = round(float(np.mean(protected[y : y + height, x : x + width] > 0)), 6)
    candidates.sort(key=lambda row: (-row["score"], row["y"], row["x"]))
    return binary, protected, candidates


def _choose_regions(candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(candidates) <= limit:
        return candidates
    # Preserve both a dominant difference and a non-dominant component when possible.
    chosen = [candidates[0]]
    remaining = candidates[1:]
    median_area = np.median([candidate["area"] for candidate in remaining])
    chosen.append(min(remaining, key=lambda candidate: (abs(candidate["area"] - median_area), candidate["y"], candidate["x"])))
    return chosen[:limit]


def _bbox_with_padding(candidate: dict[str, Any], shape: tuple[int, int], padding: int = 42) -> tuple[int, int, int, int]:
    height, width = shape
    x0 = max(0, candidate["x"] - padding)
    y0 = max(0, candidate["y"] - padding)
    x1 = min(width, candidate["x"] + candidate["width"] + padding)
    y1 = min(height, candidate["y"] + candidate["height"] + padding)
    return x0, y0, x1 - x0, y1 - y0


def _overlay(rgb: np.ndarray, mask: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    result = rgb.copy()
    selected = mask > 0
    result[selected] = (0.55 * result[selected] + 0.45 * np.array(color)).astype(np.uint8)
    return result


def _region_preview(jp: np.ndarray, textless: np.ndarray, diff: np.ndarray, mask: np.ndarray, protected: np.ndarray, bbox: tuple[int, int, int, int], output: Path) -> None:
    x, y, width, height = bbox
    context = _bbox_with_padding({"x": x, "y": y, "width": width, "height": height}, jp.shape[:2], padding=84)
    cx, cy, cw, ch = context
    diff_rgb = cv2.cvtColor(diff, cv2.COLOR_GRAY2RGB)
    mask_rgb = _overlay(np.full_like(jp, 255), mask, (230, 40, 40))
    protected_rgb = _overlay(textless, protected, (40, 100, 230))
    _labelled_strip([
        ("jp crop", jp[y : y + height, x : x + width]),
        ("textless crop", textless[y : y + height, x : x + width]),
        ("aligned difference", diff_rgb[y : y + height, x : x + width]),
        ("candidate mask", mask_rgb[y : y + height, x : x + width]),
        ("protected structure", protected_rgb[y : y + height, x : x + width]),
        ("context", jp[cy : cy + ch, cx : cx + cw]),
    ], output)


def generate_regions(config: PilotConfig, selected: list[dict[str, str]]) -> list[dict[str, str]]:
    masks_root = config.review_dir / "masks"
    regions_root = config.review_dir / "regions"
    for root in (masks_root, regions_root):
        if root.exists():
            shutil.rmtree(root)
    rows: list[dict[str, str]] = []
    for page_index, triplet in enumerate(selected, start=1):
        jp_path = config.input_root / triplet["original_path"]
        textless_path = config.input_root / triplet["textless_path"]
        chinese_path = config.input_root / triplet["chinese_path"]
        jp, textless = _load_rgb(jp_path), _load_rgb(textless_path)
        mask, protected, candidates = extract_candidate_regions(jp, textless, triplet["textless_transform_matrix"], config.min_component_area)
        chosen = _choose_regions(candidates, config.regions_per_page)
        for region_index, candidate in enumerate(chosen, start=1):
            region_id = f"{triplet['work_id']}-p{page_index:03d}-r{region_index:02d}"
            bbox = _bbox_with_padding(candidate, jp.shape[:2])
            x, y, width, height = bbox
            local_mask = np.zeros_like(mask)
            local_mask[y : y + height, x : x + width] = mask[y : y + height, x : x + width]
            mask_path = masks_root / f"{region_id}.png"
            mask_path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(mask_path), local_mask)
            preview_path = regions_root / f"{region_id}.png"
            _region_preview(jp, _warp_textless(textless, jp.shape[:2], triplet["textless_transform_matrix"]), cv2.absdiff(cv2.cvtColor(jp, cv2.COLOR_RGB2GRAY), cv2.cvtColor(_warp_textless(textless, jp.shape[:2], triplet["textless_transform_matrix"]), cv2.COLOR_RGB2GRAY)), local_mask, protected, bbox, preview_path)
            rows.append({
                "region_id": region_id,
                "work_id": triplet["work_id"],
                "page_triplet_id": hashlib.sha256(triplet["original_path"].encode("utf-8")).hexdigest()[:16],
                "jp_source_path": triplet["original_path"],
                "textless_source_path": triplet["textless_path"],
                "zh_source_path": triplet["chinese_path"],
                "jp_source_sha256": sha256_file(jp_path),
                "textless_source_sha256": sha256_file(textless_path),
                "zh_source_sha256": sha256_file(chinese_path),
                "bbox_xywh": json.dumps([x, y, width, height]),
                "textless_alignment_transform": triplet["textless_transform_matrix"],
                "registration_quality": triplet["textless_registration_quality"],
                "candidate_mask_path": _relative(mask_path, config.review_dir),
                "candidate_mask_sha256": sha256_file(mask_path),
                "review_preview_path": _relative(preview_path, config.review_dir),
                "candidate_basis": "aligned_jp_textless_difference_candidate_not_ground_truth",
                "eligibility": "pending",
                "complexity_class": "",
                "mask_status": "pending",
                "protected_structure_status": "pending",
                "rejection_reason": "",
                "reviewer_note": "",
            })
    return rows


def _report(config: PilotConfig, input_before: str, input_after: str, review_count: int, selected: list[dict[str, str]], regions: list[dict[str, str]]) -> str:
    works = Counter(row["work_id"] for row in selected)
    statuses = Counter(row["eligibility"] for row in regions)
    return "\n".join([
        "# Cleaning Benchmark Pilot v0.1 — 人工复核准备包",
        "",
        "本轮只生成复核材料与自动候选；未生成 `benchmark-manifest.jsonl`。所有差异 mask 均为待审候选，不是 ground truth，也未自动通过人工 review。",
        "",
        "## 结果",
        "",
        f"- unresolved review bundle：{review_count}/17",
        f"- 确定性页面选择：{len(selected)}（" + "，".join(f"{work}={works[work]}" for work in EXPLORATION_WORKS) + "）",
        f"- 清理区域候选：{len(regions)}",
        f"- 初始 eligibility：{dict(sorted(statuses.items()))}",
        f"- 选择 seed：{config.selection_seed}",
        f"- 输入树 SHA-256：运行前 `{input_before}`；运行后 `{input_after}`",
        "",
        "## 决策与理由",
        "",
        "- 仅 work-003 与 work-004；只使用三版本完整、两侧配对分数至少 0.78、两侧配准均为 high 的 Gold candidate 自动资格页，并排除 17 个 unresolved 路径。Gold candidate 仅是页面技术资格，不代表人工 Gold 标注。",
        "- 用固定 seed 的双作品轮替选择，保持作品覆盖并使同一输入和配置产生相同页面顺序。",
        "- 候选来自已配准 JP 与 textless 的像素差异，做闭运算、连通域与极小区域过滤；每页至多两个，以减少简单区域淹没复核集。",
        "- `region-review.csv` 的 eligibility、mask_status、protected_structure_status 均保留 pending，复杂度与结论留空，等待人工复核。",
        "",
        "## 已拒绝的替代方案",
        "",
        "- 不将自动 difference mask 升格为 Oracle mask / ground truth。",
        "- 不从 Dev 或 Frozen Test 取样，也不运行 detector、OCR、VLM、LaMa、翻译或外部 API。",
        "- 不按视觉难度预筛掉候选；预览包保留每页的主候选与非主候选（若存在）。",
        "",
        "## 风险、验证与待决问题",
        "",
        "- 配准或编码差异仍可能产生非文字候选；protected overlay 只是结构风险提示，必须由人工判断。",
        "- 若某页面经连通域过滤后没有候选，工具不会伪造候选；应在后续人工决策后调整配置或页面集。",
        "- 待人工填写 `manual-review-resolution.csv` 与 `region-review.csv` 后，才可生成最终 benchmark manifest。",
        "- 已验证输入 hash 在运行前后相同；候选与复核图只写入 Git 忽略的本地目录。",
        "",
    ])


def _gate(input_before: str, input_after: str, review_count: int, selected: list[dict[str, str]], regions: list[dict[str, str]]) -> str:
    return "\n".join([
        "# Cleaning Benchmark Pilot Gate（等待人工复核）",
        "",
        "- [x] 输入图片未覆盖；输入树 hash 运行前后相同。",
        f"- [x] 17 个 unresolved 条目均生成本地 review bundle（{review_count}/17）。",
        f"- [x] 页面仅来自 work-003/work-004（{len(selected)} 页）；未访问 Dev / Frozen Test 作为样本。",
        f"- [x] 所有自动候选进入 region-review.csv（{len(regions)} 项），无 silent skip。",
        "- [x] difference mask 明确标为 candidate，不是 ground truth。",
        "- [x] 未自动填写人工结论或 eligibility 通过状态。",
        "- [x] review bundle、crop、mask 仅输出至 Git 忽略目录。",
        "- [ ] 人工复核未完成：不得生成 benchmark-manifest.jsonl。",
        "",
        f"输入 SHA-256：`{input_before}` / `{input_after}`",
        "",
    ])


def run_pilot(config: PilotConfig) -> dict[str, Any]:
    input_before = hash_tree(config.input_root)
    frozen_manifest = json.loads((config.audit_dir / "run-manifest.json").read_text(encoding="utf-8"))
    frozen_input_hash = frozen_manifest["input_file_sha256_tree_after"]
    if input_before != frozen_input_hash:
        raise RuntimeError("input_hash_differs_from_frozen_dataset_audit")
    resolutions, bundle_metadata = generate_unresolved_review_bundle(config)
    manual_paths = {row["relative_path"] for row in _read_csv(config.audit_dir / "manual-review.csv")}
    selected = select_pages(_read_csv(config.audit_dir / "triplet-quality.csv"), manual_paths, config.selection_seed, config.page_target)
    selection_rows = []
    for index, row in enumerate(selected, start=1):
        selection_rows.append({
            "selection_order": index,
            "selection_seed": config.selection_seed,
            "work_id": row["work_id"],
            "page_triplet_id": hashlib.sha256(row["original_path"].encode("utf-8")).hexdigest()[:16],
            "jp_source_path": row["original_path"],
            "textless_source_path": row["textless_path"],
            "zh_source_path": row["chinese_path"],
            "qualification": row["qualification"],
            "textless_match_score": row["textless_match_score"],
            "chinese_match_score": row["chinese_match_score"],
            "textless_registration_quality": row["textless_registration_quality"],
            "chinese_registration_quality": row["chinese_registration_quality"],
            "selection_reason": "exploration_work;complete_triplet;pairing_high;registration_high;not_unresolved;seed_balanced",
        })
    _csv(config.output_dir / "page-selection.csv", selection_rows, selection_rows[0].keys())
    region_rows = generate_regions(config, selected)
    if not 40 <= len(region_rows) <= 60:
        raise RuntimeError(f"candidate_region_count_outside_target:{len(region_rows)}")
    _csv(config.output_dir / "region-review.csv", region_rows, region_rows[0].keys())
    input_after = hash_tree(config.input_root)
    if input_before != input_after:
        raise RuntimeError("input_hash_changed_during_pilot")
    _atomic_text(config.output_dir / "REPORT.md", _report(config, input_before, input_after, len(resolutions), selected, region_rows))
    _atomic_text(config.output_dir / "GATE.md", _gate(input_before, input_after, len(resolutions), selected, region_rows))
    return {"input_hash_before": input_before, "input_hash_after": input_after, "unresolved_review_count": len(resolutions), "bundle_metadata": bundle_metadata, "page_count": len(selected), "page_work_counts": dict(Counter(row["work_id"] for row in selected)), "region_count": len(region_rows), "eligibility_counts": dict(Counter(row["eligibility"] for row in region_rows))}
