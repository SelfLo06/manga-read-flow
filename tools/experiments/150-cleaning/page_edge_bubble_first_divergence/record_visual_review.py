#!/usr/bin/env python3
"""Freeze a maintainer visual review without mutating an isolation run."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).parent))

from core import ExperimentStop, artifact_inventory, digest, read_json, utc_now, write_json  # noqa: E402


DEFAULT_ROOT = ROOT / "data/local/runs/150-cleaning/page-edge-bubble-first-divergence-v0.1"


def record(*, isolation_run: Path, output: Path) -> Path:
    if output.exists():
        raise ExperimentStop(f"refusing to overwrite review run: {output}")
    source_manifest = read_json(isolation_run / "MANIFEST.json")
    decision = read_json(isolation_run / "artifacts/decision.json")
    metrics = read_json(isolation_run / "METRICS.json")
    if source_manifest.get("mode") != "oracle-cleaner-isolation" or source_manifest.get("oracle_injection") is not True:
        raise ExperimentStop("review source must be an oracle-cleaner-isolation run")
    check = metrics.get("cleaning_check", {})
    required_zero = ("required_residue_pixels", "unauthorized_write_pixels", "write_visible_boundary_pixels", "write_page_truncation_pixels", "actual_outside_influence_contract_pixels")
    if any(check.get(name) != 0 for name in required_zero) or not check.get("source_hash_unchanged"):
        raise ExperimentStop("automatic contract does not support a visual PASS_WITHIN_CASE")
    output.mkdir(parents=True)
    review = {
        "visual_review": {
            "status": "PASS_WITHIN_CASE", "blue_text_residue": "PASS",
            "visible_boundary_damage": "PASS", "page_truncation_damage": "PASS",
            "visible_seam_or_artifact": "PASS",
            "notes": "Minor low-contrast texture variation is visible under close inspection but is not readable as text and is acceptable for the M1 basic-cleaning target.",
        }
    }
    reference = {
        "isolation_run": str(isolation_run), "manifest_sha256": digest(isolation_run / "MANIFEST.json"),
        "metrics_sha256": digest(isolation_run / "METRICS.json"), "decision_sha256": digest(isolation_run / "artifacts/decision.json"),
    }
    write_json(output / "VISUAL_REVIEW.json", review)
    write_json(output / "METRICS.json", {"automatic_contract": check, "source_isolation_decision": decision, "source_run_reference": reference})
    write_json(output / "INTERVENTION_RESULT.json", {"case_id": source_manifest["case_id"], "mode": "oracle-cleaner-isolation-visual-review", "verdict": "PASS_WITHIN_CASE", "automatic_contract_pass": True, "visual_review": review["visual_review"], "source_run_reference": reference})
    manifest = {"schema_version": "page-edge-bubble-first-divergence-visual-review-v1", "run_id": output.name, "mode": "oracle-cleaner-isolation-visual-review", "case_id": source_manifest["case_id"], "source": source_manifest["source"], "roi_xyxy": source_manifest["roi_xyxy"], "oracle_injection": True, "injected_stages": source_manifest["injected_stages"], "source_run_reference": reference, "reviewed_at": utc_now(), "review_status": "PASS_WITHIN_CASE", "output_artifacts": artifact_inventory(output)}
    write_json(output / "MANIFEST.json", manifest)
    (output / "LOG.jsonl").write_text(f'{{"event":"visual_review_recorded","timestamp":"{utc_now()}","verdict":"PASS_WITHIN_CASE"}}\n{{"event":"run_completed","timestamp":"{utc_now()}","mode":"oracle-cleaner-isolation-visual-review"}}\n', encoding="utf-8")
    (output / "REPORT.md").write_text("# oracle-cleaner-isolation visual review\n\n## Observation\n\n自动合同通过：required residue、unauthorized write、visible boundary write、page-truncation write 均为 0，原图 hash 未变。维护者确认蓝色文字无可读残留，气泡轮廓、右下尾巴、左侧页边无损伤，正常阅读尺度下无明显接缝。\n\n## Verdict\n\n`PASS_WITHIN_CASE`。在该 case 的 accepted oracle 输入和当前 authorization 规则下，Cleaner 通过自动合同及人工视觉验收。\n\n## Project Decision\n\n不变。本结果不证明自动 Detection、Grouping 或 physical-boundary 能力，也不授权通用 M1 Cleaning gate、active pointer 或产品 artifact 更新。\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--isolation-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        run = record(isolation_run=args.isolation_run.resolve(), output=args.output.resolve())
        print(run)
        return 0
    except ExperimentStop as error:
        print(f"STOP: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
