from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import types

from PIL import Image
import pytest
import yaml

SPIKE_DIR = Path(__file__).resolve().parents[2] / "tools" / "spikes" / "yolo_model_selection"
if str(SPIKE_DIR) not in sys.path:
    sys.path.insert(0, str(SPIKE_DIR))

from build_manifest import build_manifest, infer_version, sample_id
from model_registry import find_model, load_registry
from normalize import denormalize_bbox_xyxy, normalize_bbox_xyxy
from output_layout import create_run_layout
from runners.base import classify_exception
from schemas import error_result
from smoke_test import image_dimensions, raw_record, select_sample
from runners.yoloe_ultralytics import load_model, local_only_ultralytics_asset


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


def write_registry_config(tmp_path: Path, *, asset_sha256: str | None = None) -> Path:
    asset_bytes = b"local text encoder"
    asset_sha256 = asset_sha256 or hashlib.sha256(asset_bytes).hexdigest()
    config = {
        "weights_root": "data/local",
        "assets": {
            "text_encoder": {
                "path": "models/yoloe-text-encoder/mobileclip_blt.ts",
                "source_url": "https://example.invalid/mobileclip_blt.ts",
                "expected_size_bytes": len(asset_bytes),
                "expected_sha256": asset_sha256,
            }
        },
        "models": [
            {
                "family": "YOLOE-26",
                "variants": ["N"],
                "task_type": "segmentation",
                "framework": "ultralytics",
                "supports_bbox": True,
                "supports_mask": True,
                "config_required": False,
                "config_path": None,
                "text_encoder_asset": "text_encoder",
                "weights": {"N": "models/yoloe-26/yoloe-26n-seg.pt"},
                "default_role": "smoke",
            },
            {
                "family": "YOLO-World V2.1",
                "variants": ["S"],
                "task_type": "detection",
                "framework": "mmyolo",
                "supports_bbox": True,
                "supports_mask": False,
                "config_required": True,
                "config_path": None,
                "weights": {"S": "models/yolo-world-v2.1/s.pth"},
                "default_role": "smoke",
            },
        ],
    }
    config_path = tmp_path / "models.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path


def test_registry_separates_detection_and_segmentation(tmp_path: Path) -> None:
    config_path = write_registry_config(tmp_path)
    for relative in (
        "data/local/models/yoloe-26/yoloe-26n-seg.pt",
        "data/local/models/yolo-world-v2.1/s.pth",
    ):
        file = tmp_path / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"weight")
    snapshot = load_registry(config_path, tmp_path)
    world = find_model(snapshot, "YOLO-World V2.1", "S")
    assert world["task_type"] == "detection"
    assert world["supports_mask"] is False
    assert world["config_required"] is True
    assert world["config_path"] is None
    assert world["available"] is False
    assert find_model(snapshot, "YOLOE-26", "N")["supports_mask"] is True


@pytest.mark.parametrize(
    ("field", "value"),
    (("weights_root", "/tmp/escape"), ("weights_root", "../escape"), ("weight_path", "../../escape.pt")),
)
def test_registry_rejects_unsafe_paths(tmp_path: Path, field: str, value: str) -> None:
    config_path = write_registry_config(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if field == "weights_root":
        config[field] = value
    else:
        config["models"][0]["weights"]["N"] = value
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="safe relative path"):
        load_registry(config_path, tmp_path)


def test_registry_rejects_duplicate_family_variant(tmp_path: Path) -> None:
    config_path = write_registry_config(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["models"].append(dict(config["models"][0]))
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate model"):
        load_registry(config_path, tmp_path)


def test_registry_rejects_unknown_asset_reference(tmp_path: Path) -> None:
    config_path = write_registry_config(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["models"][0]["text_encoder_asset"] = "missing"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown asset"):
        load_registry(config_path, tmp_path)


def test_registry_records_asset_hash_drift(tmp_path: Path) -> None:
    config_path = write_registry_config(tmp_path, asset_sha256="0" * 64)
    asset_path = tmp_path / "data/local/models/yoloe-text-encoder/mobileclip_blt.ts"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(b"local text encoder")
    snapshot = load_registry(config_path, tmp_path)
    assert snapshot["assets"]["text_encoder"]["integrity_status"] == "hash_mismatch"
    assert find_model(snapshot, "YOLOE-26", "N")["available"] is False


def test_yoloe_set_classes_uses_local_text_encoder_directory_and_restores_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asset = tmp_path / "encoder" / "mobileclip_blt.ts"
    asset.parent.mkdir()
    asset.write_bytes(b"encoder")
    expected_hash = hashlib.sha256(b"encoder").hexdigest()
    observed: dict[str, object] = {}

    class FakeYOLO:
        def __init__(self, weight: str) -> None:
            observed["weight"] = weight

        def set_classes(self, prompts: list[str]) -> None:
            observed["cwd"] = Path.cwd()
            observed["prompts"] = prompts
            observed["asset_visible"] = Path("mobileclip_blt.ts").is_file()
            from ultralytics.utils import downloads

            observed["resolved_asset"] = downloads.attempt_download_asset("mobileclip_blt.ts")

    fake_ultralytics = types.ModuleType("ultralytics")
    fake_utils = types.ModuleType("ultralytics.utils")
    fake_downloads = types.ModuleType("ultralytics.utils.downloads")
    original_resolver = lambda file, *args, **kwargs: f"downloaded:{file}"
    fake_downloads.attempt_download_asset = original_resolver  # type: ignore[attr-defined]
    fake_utils.downloads = fake_downloads  # type: ignore[attr-defined]
    fake_ultralytics.YOLO = FakeYOLO  # type: ignore[attr-defined]
    fake_ultralytics.utils = fake_utils  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ultralytics", fake_ultralytics)
    monkeypatch.setitem(sys.modules, "ultralytics.utils", fake_utils)
    monkeypatch.setitem(sys.modules, "ultralytics.utils.downloads", fake_downloads)
    monkeypatch.setitem(sys.modules, "torch", types.ModuleType("torch"))
    monkeypatch.setitem(sys.modules, "clip", types.ModuleType("clip"))
    original_cwd = Path.cwd()
    model = load_model(tmp_path / "weight.pt", ["text"], asset, len(b"encoder"), expected_hash)
    assert isinstance(model, FakeYOLO)
    assert observed["cwd"] == asset.parent
    assert observed["asset_visible"] is True
    assert observed["resolved_asset"] == str(asset)
    assert fake_downloads.attempt_download_asset is original_resolver  # type: ignore[attr-defined]
    assert Path.cwd() == original_cwd


def test_yoloe_local_asset_guard_rejects_unregistered_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asset = tmp_path / "mobileclip_blt.ts"
    asset.write_bytes(b"encoder")
    fake_ultralytics = types.ModuleType("ultralytics")
    fake_utils = types.ModuleType("ultralytics.utils")
    fake_downloads = types.ModuleType("ultralytics.utils.downloads")
    original_resolver = lambda file, *args, **kwargs: f"downloaded:{file}"
    fake_downloads.attempt_download_asset = original_resolver  # type: ignore[attr-defined]
    fake_utils.downloads = fake_downloads  # type: ignore[attr-defined]
    fake_ultralytics.utils = fake_utils  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ultralytics", fake_ultralytics)
    monkeypatch.setitem(sys.modules, "ultralytics.utils", fake_utils)
    monkeypatch.setitem(sys.modules, "ultralytics.utils.downloads", fake_downloads)

    with local_only_ultralytics_asset(asset):
        with pytest.raises(FileNotFoundError, match="automatic download is disabled"):
            fake_downloads.attempt_download_asset("mobileclip2_b.ts")  # type: ignore[attr-defined]
    assert fake_downloads.attempt_download_asset is original_resolver  # type: ignore[attr-defined]


def test_smoke_sample_is_fixed_to_expected_original_and_hash() -> None:
    expected = {
        "sample_id": "sample_original",
        "version": "original",
        "sha256": "abc",
        "relative_path": "work/original/page.png",
        "enabled": True,
    }
    manifest = {
        "samples": [
            {"sample_id": "sample_cleaned", "version": "cleaned", "sha256": "def", "enabled": True},
            expected,
        ]
    }
    config = {"sample_id": "sample_original", "required_version": "original", "sha256": "abc"}
    assert select_sample(manifest, config) == expected


def test_smoke_sample_rejects_manifest_hash_drift() -> None:
    manifest = {"samples": [{"sample_id": "sample_original", "version": "original", "sha256": "changed", "enabled": True}]}
    config = {"sample_id": "sample_original", "required_version": "original", "sha256": "abc"}
    with pytest.raises(ValueError, match="sha256"):
        select_sample(manifest, config)


def test_committed_configs_make_resolution_paths_and_capabilities_explicit() -> None:
    config_root = Path(__file__).resolve().parents[2] / "docs/spikes/detection-ocr/followups/yolo-open-vocabulary-model-selection/configs"
    inference = yaml.safe_load((config_root / "inference.yaml").read_text(encoding="utf-8"))
    models = yaml.safe_load((config_root / "models.yaml").read_text(encoding="utf-8"))
    assert inference["imgsz"] == 640
    assert inference["smoke_sample"]["required_version"] == "original"
    assert inference["smoke_sample"]["sha256"]
    assert models["weights_root"] == "data/local"
    assert models["assets"]["yoloe_mobileclip2_b"]["expected_size_bytes"] == 253794476
    assert models["assets"]["yoloe_mobileclip2_b"]["expected_sha256"] == "35d7f213e4d75f38514e4656ad3cb91158bd33e3805d8ac349f23b186f66982f"
    assert models["assets"]["yoloe_mobileclip_blt"]["expected_size_bytes"] == 599764649
    for model in models["models"][:2]:
        assert model["supports_bbox"] is True
        assert model["supports_mask"] is True
    assert models["models"][0]["text_encoder_asset"] == "yoloe_mobileclip2_b"
    assert models["models"][1]["text_encoder_asset"] == "yoloe_mobileclip_blt"
    world = models["models"][2]
    assert world["config_required"] is True
    assert world["config_path"] is None


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
