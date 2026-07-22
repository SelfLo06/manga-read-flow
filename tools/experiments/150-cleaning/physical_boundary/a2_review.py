#!/usr/bin/env python3
"""Read-only pre-freeze review for A2 producer/evaluator isolation."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import platform
from pathlib import Path


FORBIDDEN_PRODUCT_NAMES = {"ArtifactService", "QualityIssue", "WorkflowLoopEngine", "Cleaner", "sqlite"}
FORBIDDEN_CASE_NAMES = {"black2", "gura_color", "holdout-17", "holdout-yuitama-07", "holdout-10-9"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review(producer_path: Path, evaluator_path: Path, a1_root: Path) -> dict:
    producer_text = producer_path.read_text(encoding="utf-8")
    evaluator_text = evaluator_path.read_text(encoding="utf-8")
    producer_tree = ast.parse(producer_text)
    evaluator_tree = ast.parse(evaluator_text)
    findings: list[dict[str, str]] = []
    for forbidden in FORBIDDEN_PRODUCT_NAMES:
        if forbidden in producer_text:
            findings.append({"code": "PRODUCT_BYPASS_REFERENCE", "value": forbidden})
    for forbidden in FORBIDDEN_CASE_NAMES:
        if forbidden in producer_text:
            findings.append({"code": "CASE_SPECIFIC_RULE", "value": forbidden})
    if any(isinstance(node, ast.Name) and node.id in {"oracle", "review", "overlay"} for node in ast.walk(producer_tree)):
        findings.append({"code": "ORACLE_GENERATION_REFERENCE", "value": "producer AST name"})
    if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"produce", "main"} for node in ast.walk(evaluator_tree)):
        evaluator_calls_producer = any(isinstance(node, ast.Name) and node.id == "produce" for node in ast.walk(evaluator_tree))
        if evaluator_calls_producer:
            findings.append({"code": "EVALUATOR_CALLS_PRODUCER", "value": "produce"})
    holdout_metadata = []
    manifest = json.loads((a1_root / "MANIFEST.json").read_text(encoding="utf-8"))
    for case in manifest["cases"]:
        if case["sealed"]:
            holdout_metadata.append({"case_id": case["case_id"], "split": case["split"], "sealed": case["sealed"], "source_sha256": case["source_sha256"], "input_sha256": case["input_sha256"]})
    return {
        "schema": "physical-boundary-a2-independent-review-v0.1",
        "review_scope": "producer/evaluator source, config binding, and top-level holdout metadata only",
        "producer_sha256": sha256(producer_path),
        "evaluator_sha256": sha256(evaluator_path),
        "python": platform.python_version(),
        "findings": findings,
        "producer_oracle_free": not any(item["code"] == "ORACLE_GENERATION_REFERENCE" for item in findings),
        "evaluator_separate": not any(item["code"] == "EVALUATOR_CALLS_PRODUCER" for item in findings),
        "holdout_metadata": holdout_metadata,
        "status": "PASS" if not findings else "FAIL",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--producer", required=True, type=Path)
    parser.add_argument("--evaluator", required=True, type=Path)
    parser.add_argument("--a1-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = review(args.producer, args.evaluator, args.a1_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(result["status"])
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
