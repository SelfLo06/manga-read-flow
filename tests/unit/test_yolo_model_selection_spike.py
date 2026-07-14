from __future__ import annotations

import json
from pathlib import Path
import sys

from PIL import Image
import pytest

SPIKE_DIR = Path(__file__).resolve().parents[2] / "tools" / "spikes" / "yolo_model_selection"
if str(SPIKE_DIR) not in sys.path:
    sys.path.insert(0, str(SPIKE_DIR))

from build_manifest import build_manifest, infer_version, sample_id
from model_registry import registry
from normalize import denormalize_bbox_xyxy, normalize_bbox_xyxy
from output_layout import create_run_layout
from runners.base import classify_exception
from schemas import error_result
from smoke_test import image_dimensions, raw_record


def make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (20, 10), "white").save(path)


def test_manifest_excludes_models_and_experiment_outputs(tmp_path: Path) -> None:
    make_image(tmp_path / "work" / "original" / "page.png")
    make_image(tmp_path / "models" / "hidden.png")
    make_image(tmp_path / "yolo-model-selection" / "runs" / "old.png")
    manifest = build_manifest(tmp_path)
    assert [record["relative_path"] for record in manifest["samples"]] == ["work/original/page.png"]
    assert manifest["samples"][0]["version"] == "original"


def test_manifest_reads_metadata_for_large_trusted_local_images(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_image(tmp_path / "work" / "original" / "page.png")
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1)
    manifest = build_manifest(tmp_path)
    assert manifest["samples"][0]["width"] == 20


def test_same_file_identity_is_stable() -> None:
    assert sample_id("work/original/page.png", "abc") == sample_id("work/original/page.png", "abc")


def test_version_category_is_derived_only_from_real_version_directory_name() -> None:
    assert infer_version(Path("work/raw/page.png")) == "original"
    assert infer_version(Path("work/raw [中国翻訳]/page.png")) == "translated"
    assert infer_version(Path("work/raw [無字]/page.png")) == "cleaned"


def test_registry_separates_detection_and_segmentation(tmp_path: Path) -> None:
    for relative in (
        "models/yoloe-26/yoloe-26n-seg.pt", "models/yoloe-26/yoloe-26s-seg.pt", "models/yoloe-26/yoloe-26m-seg.pt",
        "models/yoloe-11/yoloe-11s-seg.pt", "models/yoloe-11/yoloe-11m-seg.pt",
        "models/yolo-world-v2.1/s_stage1-d1c1d7d8.pth", "models/yolo-world-v2.1/m_stage1-7e1e5299.pth",
    ):
        file = tmp_path / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"weight")
    models = registry(tmp_path)
    world = next(model for model in models if model["family"] == "YOLO-World V2.1")
    assert world["task_type"] == "detection"
    assert world["supports_mask"] is False
    assert all(model["supports_mask"] for model in models if model["family"].startswith("YOLOE"))


def test_existing_run_is_never_overwritten(tmp_path: Path) -> None:
    create_run_layout(tmp_path, "run-001")
    with pytest.raises(FileExistsError):
        create_run_layout(tmp_path, "run-001")


def test_bbox_normalization_round_trip() -> None:
    assert denormalize_bbox_xyxy(normalize_bbox_xyxy([10, 20, 50, 60], 100, 200), 100, 200) == [10, 20, 50, 60]


def test_missing_dependency_is_structured() -> None:
    result = error_result(
        run_id="run", sample_id="sample", model={}, request={}, status="dependency_missing", message="missing", missing_dependencies=["mmdet"]
    )
    assert result["status"] == "dependency_missing"
    assert result["error"]["missing_dependencies"] == ["mmdet"]


def test_oom_is_normalized() -> None:
    assert classify_exception(RuntimeError("CUDA out of memory")) == "oom"


def test_raw_record_does_not_synthesize_mask() -> None:
    result = error_result(run_id="run", sample_id="sample", model={}, request={}, status="dependency_missing", message="missing")
    assert raw_record(result)["provider_output"]["detections"] == []


def test_smoke_input_readability_check_handles_large_trusted_images(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_path = tmp_path / "page.png"
    make_image(image_path)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1)
    assert image_dimensions(image_path) == (20, 10)


def test_example_manifest_has_no_local_path_or_hash() -> None:
    example_path = Path(__file__).resolve().parents[2] / "docs/spikes/detection-ocr/followups/yolo-open-vocabulary-model-selection/manifest.example.json"
    encoded = example_path.read_text(encoding="utf-8")
    example = json.loads(encoded)
    assert "data/local" not in encoded
    assert example["samples"][0]["sha256"] == "0" * 64
