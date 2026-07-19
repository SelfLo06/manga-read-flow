from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[4]
RUNNER_PATH = (
    ROOT_DIR
    / "tools"
    / "experiments"
    / "120-grouping"
    / "text_seeded_container_association"
    / "calibrate_same_container.py"
)
CALIBRATION_ROOT = (
    ROOT_DIR / "data" / "local" / "datasets" / "120-grouping" / "text-seeded-calibration-v0.1"
)


def load_runner(name: str = "text_seeded_container_calibration"):
    spec = importlib.util.spec_from_file_location(name, RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_real_calibration_inputs_are_hash_locked_and_calibration_only():
    runner = load_runner()

    verified = runner.verify_calibration_inputs(CALIBRATION_ROOT)

    assert verified["run_id"] == "20260715T075556Z-7bb156"
    assert verified["asset_ids"] == ["cal-01", "cal-02"]
    assert verified["results_sha256"] == runner.EXPECTED_RESULTS_SHA256
    assert verified["spec_sha256"] == runner.EXPECTED_SPEC_SHA256


def test_pair_key_rejects_evaluation_assets(tmp_path: Path):
    runner = load_runner("text_seeded_container_calibration_leak")
    pair_key = tmp_path / "pairs.json"
    pair_key.write_text(
        json.dumps(
            {
                "schema_version": "text-seeded-container-calibration-pairs-v1",
                "asset_scope": ["cal-01", "case-01"],
                "pairs": [
                    {
                        "asset_id": "case-01",
                        "left_fragment_id": "p1",
                        "right_fragment_id": "p2",
                        "label": "different",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(runner.CalibrationStop, match="non-calibration asset"):
        runner.load_pair_key(pair_key)


def test_pair_key_rejects_duplicate_fragment_pairs(tmp_path: Path):
    runner = load_runner("text_seeded_container_calibration_duplicate")
    pair_key = tmp_path / "pairs.json"
    pair = {
        "asset_id": "cal-01",
        "left_fragment_id": "p1",
        "right_fragment_id": "p2",
        "label": "different",
    }
    pair_key.write_text(
        json.dumps(
            {
                "schema_version": "text-seeded-container-calibration-pairs-v1",
                "asset_scope": ["cal-01"],
                "pairs": [pair, dict(pair)],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(runner.CalibrationStop, match="duplicate calibration pair"):
        runner.load_pair_key(pair_key)


def test_actual_pair_scores_are_computed_only_for_frozen_pair_key():
    runner = load_runner("text_seeded_container_calibration_scores")

    result = runner.score_frozen_pairs(CALIBRATION_ROOT)

    assert len(result["scored_pairs"]) == 5
    assert {item["asset_id"] for item in result["scored_pairs"]} == {"cal-01", "cal-02"}
    assert {item["label"] for item in result["scored_pairs"]} == {"same", "different"}
    assert result["calibration"].status in {"FROZEN", "ALL_UNCERTAIN"}
    assert all("features" in item and "score" in item for item in result["scored_pairs"])


def test_written_lock_contains_only_calibration_sanity_outputs(tmp_path: Path):
    runner = load_runner("text_seeded_container_calibration_write")
    output = tmp_path / "calibration-lock-v0.1.json"

    payload = runner.write_calibration_lock(CALIBRATION_ROOT, output)

    assert output.is_file()
    assert payload["evaluation_asset_accessed"] is False
    assert payload["r0_run_performed"] is False
    assert len(payload["calibration_harness_sanity"]) == 6
    assert {item["asset_id"] for item in payload["calibration_harness_sanity"]} == {
        "cal-01",
        "cal-02",
    }
    assert {item["method_id"] for item in payload["calibration_harness_sanity"]} == {
        "B0",
        "B1",
        "P1",
    }
