from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from PIL import Image


ROOT_DIR = Path(__file__).resolve().parents[2]
RUNNER_PATH = (
    ROOT_DIR
    / "tools"
    / "spikes"
    / "text_seeded_container_association"
    / "freeze_s1_inputs.py"
)
GROUPING_PATH = ROOT_DIR / "tools" / "spikes" / "text_region_grouping" / "spike.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_spec(
    tmp_path: Path,
    *,
    asset_id: str = "case-01",
    extra_asset_fields: dict | None = None,
) -> Path:
    image_path = tmp_path / "images" / "case-01.png"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (120, 80), "white").save(image_path)
    asset = {
        "asset_id": asset_id,
        "relative_path": "images/case-01.png",
        "sha256": sha256_file(image_path),
        "width": 120,
        "height": 80,
    }
    asset.update(extra_asset_fields or {})
    spec_path = tmp_path / "spec.local.json"
    spec_path.write_text(
        json.dumps(
            {
                "schema_version": "text-seeded-container-s1-input-spec-v1",
                "assets": [asset],
            }
        ),
        encoding="utf-8",
    )
    return spec_path


class FakeDetector:
    mode = "FakeTextDetection"

    class Model:
        _model_name = "fake-model-v1"

    model = Model()

    def predict(self, _image_path: Path):
        return {
            "predictions": [
                {
                    "prediction_id": "p0001",
                    "bbox": {"x": 10, "y": 8, "width": 20, "height": 55},
                    "polygon": [[10, 8], [30, 8], [30, 63], [10, 63]],
                    "score": None,
                },
                {
                    "prediction_id": "p0002",
                    "bbox": {"x": 34, "y": 10, "width": 20, "height": 52},
                    "polygon": [[34, 10], [54, 10], [54, 62], [34, 62]],
                    "score": None,
                },
            ],
            "raw": {"must_not_be_persisted": True},
            "mode": self.mode,
        }


def test_freeze_run_uses_blind_inputs_and_omits_detector_raw_and_gt(tmp_path: Path):
    runner = load_module(RUNNER_PATH, "text_seeded_s1_freeze")
    grouping = load_module(GROUPING_PATH, "text_seeded_s1_grouping")
    spec_path = make_spec(tmp_path)

    result_path = runner.freeze_inputs(
        spec_path=spec_path,
        output_root=tmp_path / "runs",
        run_id="fixed-run",
        detector_factory=FakeDetector,
        grouping_module=grouping,
        environment={"test": True},
    )

    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "completed"
    assert result["input_hashes_unchanged"] is True
    assert result["provenance"]["detector"]["model_name"] == "fake-model-v1"
    assert result["assets"][0]["asset_id"] == "case-01"
    assert len(result["assets"][0]["fragments"]) == 2
    assert len(result["assets"][0]["groups"]) == 1
    serialized = json.dumps(result)
    assert "must_not_be_persisted" not in serialized
    assert "semantic_label" not in serialized
    assert "expected_text" not in serialized
    assert "overlay" not in serialized


@pytest.mark.parametrize(
    "forbidden",
    [
        {"semantic_label": "not-text"},
        {"container_count": 2},
        {"same_container": False},
        {"overlay_path": "annotator-a/overlays/case-01-overlay.png"},
    ],
)
def test_spec_rejects_evaluator_or_overlay_fields(tmp_path: Path, forbidden: dict):
    runner = load_module(RUNNER_PATH, f"text_seeded_s1_freeze_{next(iter(forbidden))}")
    spec_path = make_spec(tmp_path, extra_asset_fields=forbidden)

    with pytest.raises(runner.FreezeStop, match="unsupported asset fields"):
        runner.load_and_validate_spec(spec_path)


def test_spec_rejects_non_blind_asset_id(tmp_path: Path):
    runner = load_module(RUNNER_PATH, "text_seeded_s1_freeze_non_blind")
    spec_path = make_spec(tmp_path)
    data = json.loads(spec_path.read_text(encoding="utf-8"))
    data["assets"][0]["asset_id"] = "R0-not-text"
    spec_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(runner.FreezeStop, match="blind asset ID"):
        runner.load_and_validate_spec(spec_path)


def test_spec_accepts_blind_calibration_asset_id(tmp_path: Path):
    runner = load_module(RUNNER_PATH, "text_seeded_s1_freeze_calibration")
    spec_path = make_spec(tmp_path, asset_id="cal-01")

    spec = runner.load_and_validate_spec(spec_path)

    assert spec["assets"][0]["asset_id"] == "cal-01"


def test_spec_rejects_image_hash_mismatch(tmp_path: Path):
    runner = load_module(RUNNER_PATH, "text_seeded_s1_freeze_hash")
    spec_path = make_spec(tmp_path)
    data = json.loads(spec_path.read_text(encoding="utf-8"))
    data["assets"][0]["sha256"] = "0" * 64
    spec_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(runner.FreezeStop, match="SHA-256 mismatch"):
        runner.load_and_validate_spec(spec_path)


def test_freeze_run_refuses_to_overwrite_existing_run(tmp_path: Path):
    runner = load_module(RUNNER_PATH, "text_seeded_s1_freeze_overwrite")
    grouping = load_module(GROUPING_PATH, "text_seeded_s1_grouping_overwrite")
    spec_path = make_spec(tmp_path)
    output_root = tmp_path / "runs"
    runner.freeze_inputs(
        spec_path=spec_path,
        output_root=output_root,
        run_id="fixed-run",
        detector_factory=FakeDetector,
        grouping_module=grouping,
        environment={"test": True},
    )

    with pytest.raises(runner.FreezeStop, match="already exists"):
        runner.freeze_inputs(
            spec_path=spec_path,
            output_root=output_root,
            run_id="fixed-run",
            detector_factory=FakeDetector,
            grouping_module=grouping,
            environment={"test": True},
        )
