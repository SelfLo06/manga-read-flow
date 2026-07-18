#!/usr/bin/env python3
"""Evaluate Stage A candidates only against maintainer-labelled disputed components."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_RUN = ROOT / "data/local/physical-bubble-boundary-spike-v0.1/stage-a-run-v0.2"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    args = parser.parse_args()
    run = args.run.resolve()
    summary = json.loads((run / "stage-a-summary.json").read_text(encoding="utf-8"))
    labels = {item["component_id"]: item for item in json.loads((run / "human-review-lock.json").read_text(encoding="utf-8"))["reviews"]}
    methods = ("a1", "a2", "a5")
    metrics = {method: {"text_labeled_pixels": 0, "boundary_labeled_pixels": 0, "unknown_labeled_pixels": 0, "text_predicted_pixels": 0, "text_predicted_on_boundary_pixels": 0, "text_predicted_on_text_pixels": 0, "unresolved_text_pixels": 0, "unresolved_boundary_pixels": 0, "by_color_stratum": {}} for method in methods}
    for target in summary["targets"]:
        for component in target["components"]:
            label = labels[component["component_id"]]
            pixels = int(component["pixels"])
            category = label["human_class"]
            stratum = label["color_stratum"]
            for method in methods:
                item = metrics[method]
                predicted = int(component[f"{method}_required_text"])
                unresolved = int(component[f"{method}_unresolved"])
                if category == "TEXT_EDGE":
                    item["text_labeled_pixels"] += pixels
                    item["text_predicted_on_text_pixels"] += predicted
                    item["unresolved_text_pixels"] += unresolved
                elif category == "BUBBLE_BOUNDARY":
                    item["boundary_labeled_pixels"] += pixels
                    item["text_predicted_on_boundary_pixels"] += predicted
                    item["unresolved_boundary_pixels"] += unresolved
                else:
                    item["unknown_labeled_pixels"] += pixels
                item["text_predicted_pixels"] += predicted
                color = item["by_color_stratum"].setdefault(stratum, {"human_text_pixels": 0, "predicted_text_pixels": 0, "boundary_pixels": 0})
                if category == "TEXT_EDGE":
                    color["human_text_pixels"] += pixels
                    color["predicted_text_pixels"] += predicted
                elif category == "BUBBLE_BOUNDARY":
                    color["boundary_pixels"] += pixels
    rendered = {}
    for method, item in metrics.items():
        for stratum in ("DEEP_BLUE", "ORANGE", "ANTIALIAS_EDGE"):
            item["by_color_stratum"].setdefault(stratum, {"human_text_pixels": 0, "predicted_text_pixels": 0, "boundary_pixels": 0})
        precision_denominator = item["text_predicted_on_text_pixels"] + item["text_predicted_on_boundary_pixels"]
        rendered[method] = {
            **item,
            "false_boundary_to_text_pixels": item["text_predicted_on_boundary_pixels"],
            "disputed_text_precision": None if precision_denominator == 0 else round(item["text_predicted_on_text_pixels"] / precision_denominator, 8),
            "disputed_text_recall": None if item["text_labeled_pixels"] == 0 else round(item["text_predicted_on_text_pixels"] / item["text_labeled_pixels"], 8),
            "color_stratum_recall": {name: (None if value["human_text_pixels"] == 0 else round(value["predicted_text_pixels"] / value["human_text_pixels"], 8)) for name, value in item["by_color_stratum"].items()},
        }
    result = {
        "schema": "physical-boundary-stage-a-evaluation-v0.1",
        "human_review_lock_sha256": hashlib.sha256((run / "human-review-lock.json").read_bytes()).hexdigest(),
        "metrics_scope": "maintainer-labelled disputed components only; no claim about full-page precision/recall",
        "methods": rendered,
        "stage_a_gate": "NO_GO",
        "no_go_reasons": [
            "g002 contains human-confirmed TEXT_EDGE pixels in the frozen protected corridor; protected pixels remain non-writable",
            "A1/A2/A5 leave nonzero human-confirmed text unresolved and do not establish a safe physical-boundary correction",
            "A1/A2/A5 do not automatically prove g004 boundary components as non-text under a generic control-validated rule",
            "required control matrix has not proven a bounded general capability",
        ],
    }
    evaluation_path = run / "stage-a-evaluation.json"
    evaluation_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (run / "stage-a-evaluation-lock.json").write_text(json.dumps({"schema": "physical-boundary-stage-a-evaluation-lock-v0.1", "stage_a_evaluation_sha256": hashlib.sha256(evaluation_path.read_bytes()).hexdigest(), "human_review_lock_sha256": result["human_review_lock_sha256"], "frozen_summary_sha256": hashlib.sha256((run / "stage-a-summary.json").read_bytes()).hexdigest()}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
