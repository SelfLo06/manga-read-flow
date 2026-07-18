from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


RUNNER = Path("tools/spikes/cleaning/physical_boundary/evaluate_stage_a.py")


def test_real_stage_a_evaluator_reports_disputed_component_metrics_and_no_go(tmp_path):
    _write_stage_a(
        tmp_path,
        components=(
            _component("text", 5, a1_required=3, a1_unresolved=2),
            _component("boundary", 4, a1_required=1, a1_unresolved=3),
            _component("uncertain", 1, a1_required=0, a1_unresolved=1),
        ),
        reviews=(
            _review("text", "TEXT_EDGE", "DEEP_BLUE"),
            _review("boundary", "BUBBLE_BOUNDARY", "ANTIALIAS_EDGE"),
            _review("uncertain", "UNCERTAIN", "OTHER"),
        ),
    )

    result = _run(tmp_path)

    a1 = result["methods"]["a1"]
    assert a1["text_labeled_pixels"] == 5
    assert a1["text_predicted_on_text_pixels"] == 3
    assert a1["false_boundary_to_text_pixels"] == 1
    assert a1["unresolved_text_pixels"] == 2
    assert a1["disputed_text_precision"] == 0.75
    assert result["stage_a_gate"] == "NO_GO"
    assert (tmp_path / "stage-a-evaluation-lock.json").is_file()


def test_real_stage_a_evaluator_reports_zero_false_boundary_to_text_for_abstention(tmp_path):
    _write_stage_a(
        tmp_path,
        components=(_component("boundary", 4, a1_unresolved=4),),
        reviews=(_review("boundary", "BUBBLE_BOUNDARY", "ANTIALIAS_EDGE"),),
    )

    result = _run(tmp_path)

    assert result["methods"]["a1"]["false_boundary_to_text_pixels"] == 0
    assert result["methods"]["a1"]["unresolved_boundary_pixels"] == 4
    assert result["stage_a_gate"] == "NO_GO"


def _run(run_root: Path) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "--run", str(run_root)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _write_stage_a(run_root: Path, *, components, reviews) -> None:
    (run_root / "stage-a-summary.json").write_text(
        json.dumps({"targets": [{"components": list(components)}]}), encoding="utf-8"
    )
    (run_root / "human-review-lock.json").write_text(
        json.dumps({"reviews": list(reviews)}), encoding="utf-8"
    )


def _component(name: str, pixels: int, *, a1_required: int = 0, a1_unresolved: int = 0):
    values = {"component_id": name, "pixels": pixels}
    for method in ("a1", "a2", "a5"):
        values[f"{method}_required_text"] = a1_required if method == "a1" else 0
        values[f"{method}_unresolved"] = a1_unresolved if method == "a1" else pixels
    return values


def _review(component_id: str, human_class: str, color_stratum: str):
    return {"component_id": component_id, "human_class": human_class, "color_stratum": color_stratum}
