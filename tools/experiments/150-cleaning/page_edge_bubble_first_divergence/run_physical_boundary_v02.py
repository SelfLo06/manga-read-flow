#!/usr/bin/env python3
"""Two-case, oracle-free PhysicalBoundaryEvidence v0.2 candidate spike."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import argparse

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT))
from paddle_detection_adapter import run as detect, sha256_file  # noqa: E402
from grouping_adapter import run as group  # noqa: E402
from core import artifact_inventory, utc_now, write_json  # noqa: E402
from tools.experiments.grouping_120.text_seeded_container_association import harness, routed_association as routed  # noqa: E402

RUN_ROOT = ROOT / "data/local/runs/150-cleaning/physical-boundary-v0.2"
CASES = (
    {"case_id": "page_edge_bubble_001", "source": "data/local/sources/110-detection/real-samples-v0.1/gura_color.webp", "sha256": "6518cbe64699a9d6e878c066d828babbcf48c6d7b26332b72408bc692a3069c9"},
    {"case_id": "black2_touching_bubbles_001", "source": "data/local/sources/110-detection/real-samples-v0.1/black2.webp", "sha256": "95434f5436059b3427dd817e49e071adf795b001c9774553a9608960128965bb"},
)
POLICY = routed.RoutedPolicy(.5, .85, .65, 2, .15, .2, .2, .85)


def log(run: Path, event: str, **fields: object) -> None:
    with (run / "LOG.jsonl").open("a", encoding="utf-8") as h:
        h.write(json.dumps({"timestamp": utc_now(), "event": event, **fields}, ensure_ascii=False, sort_keys=True) + "\n")


def save_mask(mask: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((mask * 255).astype(np.uint8)).save(path)


def edge_names(mask: np.ndarray) -> list[str]:
    return [name for name, value in (("left", mask[:, 0].any()), ("right", mask[:, -1].any()), ("top", mask[0].any()), ("bottom", mask[-1, :].any())) if value]


def execute_case(run: Path, spec: dict) -> dict:
    case_dir = run / "artifacts" / spec["case_id"]
    source = ROOT / spec["source"]
    log(run, "detection_started", case_id=spec["case_id"], oracle_injection=False)
    detection = detect(source_path=source, source_sha256=spec["sha256"], output_dir=case_dir / "detection")
    candidates_path = case_dir / "detection/detection_candidates.json"
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))["candidates"]
    grouping = group(asset_id=spec["case_id"], source_path=source, source_sha256=spec["sha256"], detection_candidates_path=candidates_path, detection_candidates_sha256=sha256_file(candidates_path), output_dir=case_dir / "grouping")
    assignments = json.loads((case_dir / "grouping/grouping_assignments.json").read_text(encoding="utf-8"))
    by_candidate = {item["candidate_id"]: item["text_group_id"] for item in assignments["candidate_assignments"]}
    image = np.asarray(Image.open(source).convert("RGB"), dtype=np.uint8)
    fragments = tuple(harness.Fragment(item["candidate_id"], tuple(int(item["bbox_full_page"][key]) for key in ("x", "y", "width", "height")), tuple(tuple(point) for point in item["geometry"]), by_candidate[item["candidate_id"]], item["confidence"]) for item in candidates)
    result = routed.run_routed_association(harness.PageInput(spec["case_id"], image, fragments), POLICY)
    candidates_out = []
    for index, region in enumerate(result.container_regions, 1):
        interior = region.mask
        contour = cv2.morphologyEx(interior.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)).astype(bool)
        stem = f"bubble-{index:03d}"
        save_mask(interior, case_dir / "physical" / f"{stem}-interior.png")
        save_mask(contour, case_dir / "physical" / f"{stem}-visible-contour-candidate.png")
        candidates_out.append({"bubble_instance_candidate_id": stem, "text_group_ids": sorted({by_candidate[fid] for fid in region.fragment_ids}), "fragment_ids": list(region.fragment_ids), "interior_mask": f"physical/{stem}-interior.png", "visible_contour_candidate": f"physical/{stem}-visible-contour-candidate.png", "page_truncation_candidates": edge_names(interior), "evidence": region.evidence, "decision": "REVIEW"})
    physical = {"schema_version": "physical-boundary-evidence-v0.2-candidates-v1", "case_id": spec["case_id"], "source_sha256": spec["sha256"], "candidate_generator": "routed_association.run_routed_association (current uncalibrated implementation; REVIEW only)", "route": result.route, "topology": result.topology, "recommended_decision": "REVIEW" if candidates_out else "BLOCKED", "bubble_instance_candidates": candidates_out, "contact_or_latent_separator_candidates": [], "unknown_or_ambiguity": ["latent_separator_not_emitted_by_reused_generator"] + (["no_page_truncation_candidate"] if spec["case_id"] == "page_edge_bubble_001" and not any("left" in x["page_truncation_candidates"] for x in candidates_out) else []), "provenance": {"policy": result.diagnostics["policy"], "routed_module_sha256": sha256_file(Path(routed.__file__)), "detection_candidates_sha256": sha256_file(candidates_path), "grouping_assignments_sha256": sha256_file(case_dir / "grouping/grouping_assignments.json")}}
    write_json(case_dir / "physical_boundary_candidates.json", physical)
    log(run, "physical_candidates_frozen", case_id=spec["case_id"], bubble_candidate_count=len(candidates_out))
    return {"case_id": spec["case_id"], "detection_candidate_count": detection["candidate_count"], "text_group_count": grouping["automatic_text_group_count"], "physical": physical}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", choices=[item["case_id"] for item in CASES])
    parser.add_argument("--run-id")
    args = parser.parse_args()
    selected = [item for item in CASES if args.case_id is None or item["case_id"] == args.case_id]
    run = RUN_ROOT / (args.run_id or "20260719T0700-two-case-spike-v0.2")
    if run.exists():
        print(f"STOP: refusing to overwrite {run}", file=sys.stderr); return 2
    (run / "artifacts").mkdir(parents=True)
    try:
        observed = [execute_case(run, item) for item in selected]
        log(run, "oracle_evaluation_started", execution_oracle_access=False)
        # Evaluation is intentionally deferred; this run only freezes candidates.
        manifest = {"schema_version": "physical-boundary-evidence-v0.2-run-v1", "run_id": run.name, "oracle_injection": False, "execution_inputs": "full_page source + frozen Detection candidates + frozen text groups", "candidate_artifacts": artifact_inventory(run), "status": "CANDIDATES_FROZEN_PENDING_OFFLINE_ORACLE_EVALUATION"}
        write_json(run / "MANIFEST.json", manifest); write_json(run / "METRICS.json", {"cases": observed})
        (run / "REPORT.md").write_text("# PhysicalBoundaryEvidence v0.2 two-case Spike\n\nCandidates were generated from full-page sources, frozen Detection candidates, and frozen text groups without oracle access. All candidates are `REVIEW` only; offline oracle evaluation remains a separate step.\n", encoding="utf-8")
        log(run, "run_completed", status=manifest["status"]); print(run); return 0
    except Exception as error:
        write_json(run / "FAILURE.json", {"type": type(error).__name__, "message": str(error)})
        log(run, "execution_failure", error_type=type(error).__name__, message=str(error)); print(f"STOP: {error}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
