from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont


BBox = tuple[int, int, int, int]


@dataclass(frozen=True)
class LocalRoutingPolicy:
    """Static Goal 7 policy. It qualifies local work; it does not find containers."""

    neighbor_gap_scale: float = 2.5
    min_scale_ratio: float = 0.40
    max_pair_area_ratio: float = 0.12
    max_local_seed_area_ratio: float = 0.10
    roi_padding_scale: float = 2.5
    max_roi_pixels: int = 262_144
    max_queue_entries: int = 500_000
    working_memory_budget_mb: int = 511


def _bbox(raw: dict[str, Any]) -> BBox:
    x = int(raw["x"])
    y = int(raw["y"])
    return x, y, x + int(raw["width"]), y + int(raw["height"])


def _bbox_json(box: BBox) -> dict[str, int]:
    x1, y1, x2, y2 = box
    return {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}


def _union(boxes: Iterable[BBox]) -> BBox:
    items = list(boxes)
    return (
        min(item[0] for item in items),
        min(item[1] for item in items),
        max(item[2] for item in items),
        max(item[3] for item in items),
    )


def _area(box: BBox) -> int:
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def _gap(first: BBox, second: BBox) -> float:
    dx = max(first[0] - second[2], second[0] - first[2], 0)
    dy = max(first[1] - second[3], second[1] - first[3], 0)
    return math.hypot(dx, dy)


def _fragment_scale(fragment: dict[str, Any]) -> float:
    box = _bbox(fragment["bbox"])
    return float(max(1, min(box[2] - box[0], box[3] - box[1])))


def _group_views(asset: dict[str, Any]) -> list[dict[str, Any]]:
    fragments = {item["fragment_id"]: item for item in asset["fragments"]}
    views: list[dict[str, Any]] = []
    for group in asset["groups"]:
        members = [fragments[item] for item in group["ordered_fragment_ids"] if item in fragments]
        scales = sorted(_fragment_scale(item) for item in members)
        scale = scales[len(scales) // 2] if scales else 1.0
        views.append(
            {
                "group_id": group["group_id"],
                "fragment_ids": list(group["ordered_fragment_ids"]),
                "bbox": _bbox(group["bbox"]),
                "scale": scale,
                "orientation": group.get("orientation", "unknown"),
                "uncertainty_tags": list(group.get("uncertainty_tags", [])),
                "members": members,
            }
        )
    return sorted(views, key=lambda item: (item["bbox"][1], item["bbox"][0], item["group_id"]))


def _has_oversized_seed(view: dict[str, Any], page_area: int, policy: LocalRoutingPolicy) -> bool:
    return any(_area(_bbox(item["bbox"])) / page_area > policy.max_local_seed_area_ratio for item in view["members"])


def _pairable(
    first: dict[str, Any],
    second: dict[str, Any],
    page_area: int,
    policy: LocalRoutingPolicy,
) -> tuple[bool, float]:
    scale_min = max(1.0, min(first["scale"], second["scale"]))
    scale_ratio = min(first["scale"], second["scale"]) / max(first["scale"], second["scale"])
    normalized_gap = _gap(first["bbox"], second["bbox"]) / scale_min
    pair_area_ratio = _area(_union([first["bbox"], second["bbox"]])) / page_area
    valid = (
        normalized_gap <= policy.neighbor_gap_scale
        and scale_ratio >= policy.min_scale_ratio
        and pair_area_ratio <= policy.max_pair_area_ratio
    )
    return valid, normalized_gap


def _local_clusters(views: list[dict[str, Any]], page_area: int, policy: LocalRoutingPolicy) -> list[list[dict[str, Any]]]:
    """Build disjoint local pairs using mutual nearest neighbours; never page chains."""

    eligible = [item for item in views if not _has_oversized_seed(item, page_area, policy)]
    nearest: dict[str, str] = {}
    for first in eligible:
        candidates: list[tuple[float, str]] = []
        for second in eligible:
            if first is second:
                continue
            valid, score = _pairable(first, second, page_area, policy)
            if valid:
                candidates.append((score, second["group_id"]))
        if candidates:
            nearest[first["group_id"]] = min(candidates)[1]

    by_id = {item["group_id"]: item for item in views}
    used: set[str] = set()
    clusters: list[list[dict[str, Any]]] = []
    for view in views:
        group_id = view["group_id"]
        if group_id in used:
            continue
        other_id = nearest.get(group_id)
        if other_id and nearest.get(other_id) == group_id and other_id not in used:
            clusters.append([view, by_id[other_id]])
            used.update((group_id, other_id))
        else:
            clusters.append([view])
            used.add(group_id)
    return sorted(clusters, key=lambda items: (_union(item["bbox"] for item in items)[1], _union(item["bbox"] for item in items)[0]))


def _make_roi(seed_box: BBox, width: int, height: int, scale: float, padding_scale: float) -> BBox:
    padding = int(round(scale * padding_scale))
    return (
        max(0, seed_box[0] - padding),
        max(0, seed_box[1] - padding),
        min(width, seed_box[2] + padding),
        min(height, seed_box[3] + padding),
    )


def _l1_projection(roi: BBox, max_pixels: int) -> tuple[float, int]:
    source_width = max(1, roi[2] - roi[0])
    source_height = max(1, roi[3] - roi[1])
    source_pixels = source_width * source_height
    scale = min(1.0, math.sqrt(max_pixels / source_pixels))
    l1_width = max(1, math.floor(source_width * scale))
    l1_height = max(1, math.floor(source_height * scale))
    return scale, l1_width * l1_height


def route_asset(asset: dict[str, Any], policy: LocalRoutingPolicy) -> dict[str, Any]:
    width = int(asset["width"])
    height = int(asset["height"])
    page_area = max(1, width * height)
    views = _group_views(asset)
    fragments = {item["fragment_id"]: item for item in asset["fragments"]}
    clusters: list[dict[str, Any]] = []

    for index, members in enumerate(_local_clusters(views, page_area, policy), start=1):
        seed_box = _union(item["bbox"] for item in members)
        scale = max(1.0, sorted(item["scale"] for item in members)[len(members) // 2])
        roi = _make_roi(seed_box, width, height, scale, policy.roi_padding_scale)
        l1_scale, estimated_roi_pixels = _l1_projection(roi, policy.max_roi_pixels)
        fragment_ids = [fragment_id for item in members for fragment_id in item["fragment_ids"]]
        oversized = any(
            _area(_bbox(fragments[fragment_id]["bbox"])) / page_area > policy.max_local_seed_area_ratio
            for fragment_id in fragment_ids
            if fragment_id in fragments
        )
        if oversized:
            topology = "single" if len(members) == 1 else "unresolved"
            route = "LOCAL_ABSTENTION"
            reason = "oversized_local_seed"
            would_run_b1 = False
        elif len(members) > 1:
            topology = "unresolved"
            route = "LOCAL_REVIEW_REQUIRED"
            reason = "local_topology_unresolved"
            would_run_b1 = True
        else:
            topology = "single"
            route = "LOCAL_B1_CANDIDATE"
            reason = "local_geometry_valid"
            would_run_b1 = True

        clusters.append(
            {
                "page_id": asset["asset_id"],
                "cluster_id": f'{asset["asset_id"]}__lc{index:03d}',
                "group_ids": [item["group_id"] for item in members],
                "fragment_ids": fragment_ids,
                "local_bbox": _bbox_json(seed_box),
                "local_roi": _bbox_json(roi),
                "l1_scale": round(l1_scale, 6),
                "local_topology": topology,
                "route": route,
                "reason": reason,
                "estimated_roi_pixels": estimated_roi_pixels,
                "resource_budget": {
                    "max_roi_pixels": policy.max_roi_pixels,
                    "max_queue_entries": policy.max_queue_entries,
                    "working_memory_budget_mb": policy.working_memory_budget_mb,
                },
                "would_run_b1": would_run_b1,
            }
        )

    return {
        "page_id": asset["asset_id"],
        "page_decision": "AGGREGATE_ONLY",
        "cluster_count": len(clusters),
        "clusters": clusters,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_frozen_s1(results_path: Path, root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("status") != "completed" or not payload.get("input_hashes_unchanged"):
        raise RuntimeError("Frozen S1 run is not completed/unchanged")
    expected = payload["input_hashes_before"]
    observed: dict[str, str] = {}
    for asset in payload["assets"]:
        image = root / asset["relative_path"]
        observed[asset["asset_id"]] = _sha256(image)
        if observed[asset["asset_id"]] != expected[asset["asset_id"]]:
            raise RuntimeError(f'Frozen image hash changed: {asset["asset_id"]}')
    observed["results"] = _sha256(results_path)
    return observed


def run_phase_a(results_path: Path, root: Path, output_dir: Path, policy: LocalRoutingPolicy) -> Path:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite Phase A output: {output_dir}")
    payload = json.loads(results_path.read_text(encoding="utf-8"))
    verified_hashes = _verify_frozen_s1(results_path, root, payload)
    pages = [route_asset(asset, policy) for asset in payload["assets"]]
    all_clusters = [cluster for page in pages for cluster in page["clusters"]]
    route_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    for cluster in all_clusters:
        route_counts[cluster["route"]] = route_counts.get(cluster["route"], 0) + 1
        reason_counts[cluster["reason"]] = reason_counts.get(cluster["reason"], 0) + 1

    output = {
        "schema_version": "goal7-local-routing-phase-a-v1",
        "status": "COMPLETE_STATIC_ONLY",
        "contract": {
            "detection_rerun": False,
            "b1_executed": False,
            "cleaning_executed": False,
            "page_route_allowed": False,
        },
        "source": {
            "results_path": str(results_path),
            "s1_run_id": payload["run_id"],
            "verified_hashes": verified_hashes,
        },
        "policy": asdict(policy),
        "summary": {
            "page_count": len(pages),
            "group_count": sum(len(asset["groups"]) for asset in payload["assets"]),
            "cluster_count": len(all_clusters),
            "route_counts": route_counts,
            "reason_counts": reason_counts,
            "page_global_extreme_abstention_count": 0,
            "page_global_topology_block_count": 0,
        },
        "pages": pages,
    }
    output_dir.mkdir(parents=True)
    matrix_path = output_dir / "PHASE-A-MATRIX.json"
    matrix_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return matrix_path


def _select_review_clusters(matrix: dict[str, Any], count: int = 24) -> list[dict[str, Any]]:
    clusters = [cluster for page in matrix["pages"] for cluster in page["clusters"]]
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()

    def take(items: Iterable[dict[str, Any]], limit: int) -> None:
        pool = [item for item in items if item["cluster_id"] not in selected_ids]
        while pool and len([existing for existing in selected if existing.get("_round") == round_id]) < limit:
            page_counts: dict[str, int] = {}
            for existing in selected:
                page_counts[existing["page_id"]] = page_counts.get(existing["page_id"], 0) + 1
            item = min(pool, key=lambda candidate: (page_counts.get(candidate["page_id"], 0), candidate["page_id"], candidate["cluster_id"]))
            copied = dict(item)
            copied["_round"] = round_id
            selected.append(copied)
            selected_ids.add(item["cluster_id"])
            pool.remove(item)

    round_id = "abstention"
    take((item for item in clusters if item["route"] == "LOCAL_ABSTENTION"), 2)
    round_id = "review"
    priority_reviews = [item for item in clusters if item["route"] == "LOCAL_REVIEW_REQUIRED" and item["page_id"] in {"case-10", "case-26", "case-38"}]
    take(priority_reviews, 4)
    take((item for item in clusters if item["route"] == "LOCAL_REVIEW_REQUIRED"), 8)
    round_id = "candidate"
    interior = [
        item
        for item in clusters
        if item["route"] == "LOCAL_B1_CANDIDATE" and item["page_id"] not in {"case-01", "case-40"}
    ]
    take(interior, count - len(selected))
    round_id = "fill"
    take(clusters, count - len(selected))
    return selected[:count]


def _crop_with_overlay(image: Image.Image, cluster: dict[str, Any]) -> Image.Image:
    roi = _bbox(cluster["local_roi"])
    box = _bbox(cluster["local_bbox"])
    crop = image.crop(roi).convert("RGB")
    draw = ImageDraw.Draw(crop)
    local_box = (box[0] - roi[0], box[1] - roi[1], box[2] - roi[0], box[3] - roi[1])
    stroke = max(2, round(max(crop.size) / 300))
    draw.rectangle(local_box, outline=(255, 45, 45), width=stroke)
    draw.rectangle((0, 0, max(0, crop.width - 1), max(0, crop.height - 1)), outline=(0, 210, 255), width=stroke)
    return crop


def _fit_thumbnail(image: Image.Image, width: int, height: int) -> Image.Image:
    copy = image.copy()
    copy.thumbnail((width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height), "white")
    canvas.paste(copy, ((width - copy.width) // 2, (height - copy.height) // 2))
    return canvas


def build_review_pack(matrix_path: Path, s1_results: Path, root: Path, output_dir: Path) -> Path:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite review pack: {output_dir}")
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    s1 = json.loads(s1_results.read_text(encoding="utf-8"))
    _verify_frozen_s1(s1_results, root, s1)
    assets = {asset["asset_id"]: asset for asset in s1["assets"]}
    selected = _select_review_clusters(matrix)
    output_dir.mkdir(parents=True)
    images_dir = output_dir / "images"
    images_dir.mkdir()

    tile_width, tile_height = 420, 360
    sheet = Image.new("RGB", (tile_width * 4, tile_height * 6), "white")
    sheet_draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=16)
    index_items: list[dict[str, Any]] = []
    form_lines = [
        "# Goal 7 Phase A 人工冻结表",
        "",
        "红框 = 文字组/局部 cluster；青框 = local ROI 边缘。本包不展示 B1 结果，也不代表已找到容器。",
        "",
        "每项请从以下选择中各选一个：",
        "",
        "- `ContentRole`: `ORDINARY_DIALOGUE` / `CAPTION_LABEL` / `SFX_DECORATIVE` / `NOT_TEXT` / `UNCERTAIN`",
        "- `ExpectedTask`: `COARSE_CONTAINER` / `BOUNDED_SUPPORT` / `LOCAL_SKIP` / `UNCERTAIN`",
        "- `Topology`: `SAME` / `DIFFERENT` / `N_A` / `UNCERTAIN`",
        "- `PhaseB`: `YES` / `NO`",
        "",
        "不要判断像素级 mask，也不要根据 route 迁就答案。若图中红框不是文字，直接选 `NOT_TEXT + LOCAL_SKIP + N_A + NO`。",
        "",
    ]

    for position, cluster in enumerate(selected, start=1):
        review_id = f"G7-{position:03d}"
        asset = assets[cluster["page_id"]]
        source = root / asset["relative_path"]
        with Image.open(source) as image:
            crop = _crop_with_overlay(image, cluster)
        image_name = f"{review_id}.png"
        crop.save(images_dir / image_name)
        thumb = _fit_thumbnail(crop, 400, 280)
        column = (position - 1) % 4
        row = (position - 1) // 4
        x = column * tile_width
        y = row * tile_height
        sheet.paste(thumb, (x + 10, y + 55))
        title = f"{review_id} | {cluster['page_id']} | {cluster['cluster_id'].split('__')[-1]}"
        subtitle = f"{cluster['route']} | groups={len(cluster['group_ids'])}"
        sheet_draw.text((x + 10, y + 8), title, fill="black", font=font)
        sheet_draw.text((x + 10, y + 29), subtitle, fill="black", font=font)

        clean_cluster = {key: value for key, value in cluster.items() if key != "_round"}
        index_items.append(
            {
                "review_id": review_id,
                "selection_bucket": cluster.get("_round"),
                "image": f"images/{image_name}",
                **clean_cluster,
            }
        )
        form_lines.extend(
            [
                f"## {review_id} — {cluster['page_id']} / {cluster['cluster_id']}",
                "",
                f"![{review_id}](images/{image_name})",
                "",
                f"- Static route（只供核对）: `{cluster['route']}` / `{cluster['reason']}`",
                "- ContentRole: `未填`",
                "- ExpectedTask: `未填`",
                "- Topology: `未填`",
                "- PhaseB: `未填`",
                "- Note: ",
                "",
            ]
        )

    sheet.save(output_dir / "CONTACT-SHEET.png")
    index = {
        "schema_version": "goal7-phase-a-review-pack-v1",
        "status": "AWAITING_HUMAN_LABELS",
        "source_matrix_sha256": _sha256(matrix_path),
        "source_s1_results_sha256": _sha256(s1_results),
        "case_count": len(index_items),
        "items": index_items,
    }
    (output_dir / "INDEX.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    form_path = output_dir / "FORM.md"
    form_path.write_text("\n".join(form_lines), encoding="utf-8")
    return form_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Goal 7 local static association routing")
    subparsers = parser.add_subparsers(dest="command", required=True)
    phase_a = subparsers.add_parser("phase-a")
    phase_a.add_argument("--s1-results", type=Path, required=True)
    phase_a.add_argument("--root", type=Path, required=True)
    phase_a.add_argument("--output-dir", type=Path, required=True)
    review_pack = subparsers.add_parser("review-pack")
    review_pack.add_argument("--matrix", type=Path, required=True)
    review_pack.add_argument("--s1-results", type=Path, required=True)
    review_pack.add_argument("--root", type=Path, required=True)
    review_pack.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "phase-a":
        path = run_phase_a(args.s1_results, args.root, args.output_dir, LocalRoutingPolicy())
        print(path)
    elif args.command == "review-pack":
        path = build_review_pack(args.matrix, args.s1_results, args.root, args.output_dir)
        print(path)


if __name__ == "__main__":
    main()
