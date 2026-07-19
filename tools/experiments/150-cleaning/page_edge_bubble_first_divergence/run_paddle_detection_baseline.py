#!/usr/bin/env python3
"""Run the reusable Paddle Detection spike, then evaluate its frozen artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).parent))
from core import artifact_inventory, full_to_roi, load_accepted_oracle, load_case, utc_now, write_json  # noqa: E402
from paddle_detection_adapter import DetectionAdapterError, run as run_detection  # noqa: E402

CASE_FILE = ROOT / "data/local/datasets/150-cleaning/page-edge-bubble-v0.1/cases.json"
ORACLE = ROOT / "data/local/datasets/150-cleaning/page-edge-bubble-v0.1/oracles/page_edge_bubble_v0.1/accepted-v1"
RUN_ROOT = ROOT / "data/local/runs/150-cleaning/page-edge-bubble-first-divergence-v0.1"


def _git(args: list[str]) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False).stdout.strip()


def _log(run: Path, event: str, **fields: object) -> None:
    with (run / "LOG.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"timestamp": utc_now(), "event": event, **fields}, ensure_ascii=False, sort_keys=True) + "\n")


def _bbox_mask(candidates: list[dict], shape: tuple[int, int]) -> np.ndarray:
    result = np.zeros(shape, dtype=bool)
    for candidate in candidates:
        box = candidate["bbox_full_page"]
        x0, y0 = int(np.floor(box["x"])), int(np.floor(box["y"]))
        x1, y1 = int(np.ceil(box["x"] + box["width"])), int(np.ceil(box["y"] + box["height"]))
        result[y0:y1, x0:x1] = True
    return result


def _evaluate(candidates: list[dict], case, oracle, page_shape: tuple[int, int]) -> dict:
    predicted = _bbox_mask(candidates, page_shape)
    roi_predicted = full_to_roi(predicted, case)
    core, fringe, required = (oracle.masks[name] for name in ("text_core", "text_fringe", "text_required"))

    def coverage(mask: np.ndarray) -> dict:
        covered = int((roi_predicted & mask).sum())
        total = int(mask.sum())
        return {"covered_pixels": covered, "total_pixels": total, "ratio": 0.0 if total == 0 else round(covered / total, 8)}

    target_count = sum(bool((full_to_roi(_bbox_mask([candidate], page_shape), case) & required).any()) for candidate in candidates)
    return {
        "execution_status": "SUCCESS",
        "candidate_count": len(candidates),
        "geometry_evaluation": "bbox_rasterized_region_only_not_pixel_text_support",
        "core_coverage": coverage(core),
        "fringe_coverage": coverage(fringe),
        "required_coverage": coverage(required),
        "unmatched_required_pixels": int((required & ~roi_predicted).sum()),
        "target_candidate_count": target_count,
        "contamination": {
            "roi_non_target_covered_pixels": int((roi_predicted & ~required).sum()),
            "full_page_candidate_covered_pixels": int(predicted.sum()),
        },
    }


def classify_detection_outcome(detection: dict) -> tuple[dict | None, dict | None]:
    """Only hard geometry misses are divergence; bbox contamination is a metric."""
    if detection["target_candidate_count"] == 0:
        return ({"stage": "detection", "type": "no_target_candidate_coverage", "evidence": [{"artifact": "artifacts/detection_candidates.json", "metric": "target_candidate_count", "observed": 0, "oracle": "required text geometry exists"}]}, None)
    if detection["unmatched_required_pixels"]:
        return ({"stage": "detection", "type": "required_geometry_uncovered", "evidence": [{"artifact": "METRICS.json", "metric": "unmatched_required_pixels", "observed": detection["unmatched_required_pixels"], "oracle": 0}]}, None)
    return (None, {"stage": "grouping", "type": "automatic_grouping_adapter_not_available"})


def _failure(run: Path, run_id: str, error: Exception) -> int:
    failure = {"schema_version": "page-edge-bubble-auto-detection-observability-v1", "run_id": run_id, "execution_failure": {"stage": "detection", "type": type(error).__name__, "message": str(error)}, "first_observed_divergence": None, "earliest_execution_gap": None, "causality": {"established": False}}
    write_json(run / "FIRST_DIVERGENCE.json", failure)
    write_json(run / "METRICS.json", {"input": {}, "detection": {"execution_status": "FAILURE", "candidate_count": None}, "grouping": {"status": "NOT_RUN"}})
    write_json(run / "MANIFEST.json", {"schema_version": "page-edge-bubble-auto-detection-observability-v1", "run_id": run_id, "oracle_injection": False, "stage_execution_statuses": {"detection": "FAILURE", "grouping": "NOT_RUN"}})
    (run / "REPORT.md").write_text(f"# page-edge-bubble auto Detection baseline\n\n## Observation\n\nThe existing Paddle Detection spike failed before candidates were produced: `{type(error).__name__}: {error}`.\n\n## Verdict\n\nThis is an execution failure, not a first observed divergence.\n", encoding="utf-8")
    _log(run, "execution_failure", error_type=type(error).__name__, message=str(error))
    print(f"STOP: {error}", file=sys.stderr)
    return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id")
    args = parser.parse_args()
    run_id = args.run_id or f"{utc_now().replace(':', '').replace('-', '')}-auto-baseline-paddle-detection-v0.1-{uuid4().hex[:8]}"
    run = RUN_ROOT / run_id
    if run.exists():
        print(f"STOP: refusing to overwrite run: {run}", file=sys.stderr)
        return 2
    (run / "artifacts").mkdir(parents=True)
    try:
        case = load_case(CASE_FILE, ROOT)
        _log(run, "source_integrity_verified", source_sha256=case.source_sha256, algorithm_input="full_page")
        _log(run, "detection_started", oracle_injection=False)
        execution = run_detection(source_path=case.source, source_sha256=case.source_sha256, output_dir=run / "artifacts")
        execution_artifacts = artifact_inventory(run)
        _log(run, "detection_artifacts_frozen", candidate_count=execution["candidate_count"], artifacts=sorted(execution_artifacts))
        # This deliberately is the first oracle access: detection files already exist and have hashes.
        _log(run, "oracle_evaluation_started", execution_oracle_access=False)
        oracle = load_accepted_oracle(case, ORACLE)
        candidate_data = json.loads((run / "artifacts/detection_candidates.json").read_text(encoding="utf-8"))
        with Image.open(case.source) as image:
            page_shape = (image.height, image.width)
        metrics = {"input": {"source_hash_matches_case": True, "roi_is_evaluation_only": True}, "detection": _evaluate(candidate_data["candidates"], case, oracle, page_shape)}
        detection = metrics["detection"]
        first, gap = classify_detection_outcome(detection)
        metrics["grouping"] = {"status": "NOT_AVAILABLE", "reason": "scope excludes implementing a Grouping adapter"}
        first_divergence = {"case_id": case.case_id, "run_id": run_id, "first_observed_divergence": first, "earliest_execution_gap": gap, "execution_failure": None, "causality": {"established": False, "reason": "single-stage observation; no intervention executed"}}
        manifest = {"schema_version": "page-edge-bubble-auto-detection-observability-v1", "run_id": run_id, "case_id": case.case_id, "source": {"path": case.source_relative, "sha256": case.source_sha256}, "roi_xyxy": list(case.roi), "code_revision": _git(["rev-parse", "HEAD"]), "branch": _git(["branch", "--show-current"]), "working_tree_status": _git(["status", "--short"]), "detection_implementation": execution["implementation"], "model_provider_version": execution["provider_version"], "oracle_injection": False, "execution_inputs": {"source_path": case.source_relative, "source_sha256": case.source_sha256, "provider": "existing PaddleDetector spike"}, "evaluation_inputs": {"oracle_manifest_sha256": oracle.manifest_sha256, "oracle_version": "accepted-v1"}, "stage_execution_statuses": {"detection": "SUCCESS", "grouping": "NOT_AVAILABLE"}, "stop_stage": "detection" if first else "grouping", "stop_reason": first["type"] if first else gap["type"], "output_artifacts": execution_artifacts}
        write_json(run / "METRICS.json", metrics)
        write_json(run / "FIRST_DIVERGENCE.json", first_divergence)
        write_json(run / "MANIFEST.json", manifest)
        (run / "REPORT.md").write_text(f"# page-edge-bubble auto Detection baseline\n\n## Capability investigation\n\nThe product source has no executable Detection Provider Adapter. This run reused `tools/experiments/130-ocr/detection_ocr/spike.py:PaddleDetector` with its already-installed `paddleocr` runtime and cached PP-OCRv6 detection model. YOLOE is deprecated and intentionally excluded from this experiment's conclusion. No historical artifact was replayed.\n\n## Observation\n\nPaddle Detection ran on the full original page. Candidate count: `{detection['candidate_count']}`; required geometry unmatched pixels: `{detection['unmatched_required_pixels']}`. Accepted oracle data was loaded only after Detection artifacts were written and hashed.\n\n## Verdict\n\nfirst observed divergence: `{first['type'] if first else 'none'}`. earliest execution gap: `{gap['stage'] if gap else 'none'}`. Bbox coverage is geometric evaluation only, not pixel-text support.\n\n## Project Decision\n\nUnchanged. This single case does not validate general Detection or authorize Grouping, physical-boundary, Cleaner, product artifacts, or active-pointer updates.\n", encoding="utf-8")
        _log(run, "oracle_evaluation_finished", first_observed_divergence=None if first is None else "detection", earliest_execution_gap=None if gap is None else gap["stage"])
        _log(run, "run_completed", stop_stage=manifest["stop_stage"], stop_reason=manifest["stop_reason"])
        print(run)
        return 0
    except (DetectionAdapterError, Exception) as error:
        return _failure(run, run_id, error)


if __name__ == "__main__":
    raise SystemExit(main())
