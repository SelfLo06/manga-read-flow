import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT_DIR / "tools" / "dev" / "build_detection_ocr_ground_truth.py"


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def base_real_manifest() -> dict:
    return {
        "version": "1.0",
        "terminology": {"ground_truth": "expected output"},
        "reading_order_policy": {"page": "top_to_bottom"},
        "comparison_policy": {"core_ocr_text": "normalized text"},
        "annotation_status": {"real_assets": "OCR text ready; bbox pending manual annotation"},
        "assets": [
            {
                "file_name": "black1.webp",
                "relative_path": "real/black1.webp",
                "source_type": "real",
                "width": 100,
                "height": 120,
                "color_mode": "RGB",
                "scenario_tags": ["real"],
                "annotation_status": "ocr_text_ready_bbox_pending",
                "regions": [
                    {
                        "region_id": "black1_r01",
                        "region_type": "dialogue_bubble",
                        "bbox": {"x": 1, "y": 2, "width": 3, "height": 4},
                        "bbox_status": "manually_annotated",
                        "bbox_semantics": "text_container_region",
                        "include_in_core_ocr_score": True,
                        "expected_text": "テスト",
                        "expected_text_lines": ["テスト"],
                        "normalized_text": "テスト",
                    }
                ],
            }
        ],
    }


def base_generated_manifest() -> dict:
    return {
        "version": "1.0",
        "assets": [
            {
                "file_name": "synthetic_01_clean_dialogue.webp",
                "relative_path": "generated/synthetic_01_clean_dialogue.webp",
                "source_type": "synthetic",
                "width": 100,
                "height": 120,
                "color_mode": "RGB",
                "scenario_tags": ["synthetic"],
                "regions": [
                    {
                        "region_id": "s01_r01",
                        "region_type": "dialogue_bubble",
                        "bbox": {"x": 1, "y": 2, "width": 3, "height": 4},
                        "bbox_semantics": "text_container_region",
                        "expected_text": "こんにちは",
                        "expected_text_lines": ["こんにちは"],
                        "normalized_text": "こんにちは",
                    }
                ],
            }
        ],
    }


def prepare_sample_tree(tmp_path: Path, real_manifest: dict, generated_manifest: dict) -> None:
    (tmp_path / "real" / "black1.webp").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "real" / "black1.webp").write_bytes(b"real")
    (tmp_path / "generated" / "synthetic_01_clean_dialogue.webp").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "generated" / "synthetic_01_clean_dialogue.webp").write_bytes(b"synthetic")
    write_json(tmp_path / "real" / "manifest.json", real_manifest)
    write_json(tmp_path / "generated" / "manifest.json", generated_manifest)


def test_build_detection_ocr_ground_truth_merges_without_modifying_inputs(tmp_path):
    real_manifest = base_real_manifest()
    generated_manifest = base_generated_manifest()
    prepare_sample_tree(tmp_path, real_manifest, generated_manifest)

    real_before = json.loads((tmp_path / "real" / "manifest.json").read_text(encoding="utf-8"))
    generated_before = json.loads((tmp_path / "generated" / "manifest.json").read_text(encoding="utf-8"))

    subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--samples-dir", str(tmp_path)],
        cwd=ROOT_DIR,
        check=True,
    )
    first_output = (tmp_path / "detection_ocr_ground_truth.json").read_text(encoding="utf-8")
    subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--samples-dir", str(tmp_path)],
        cwd=ROOT_DIR,
        check=True,
    )
    second_output = (tmp_path / "detection_ocr_ground_truth.json").read_text(encoding="utf-8")

    assert first_output == second_output

    output = json.loads(second_output)
    assert [asset["source_type"] for asset in output["assets"]] == ["synthetic", "real"]
    assert [asset["relative_path"] for asset in output["assets"]] == [
        "generated/synthetic_01_clean_dialogue.webp",
        "real/black1.webp",
    ]
    assert sum(len(asset["regions"]) for asset in output["assets"]) == 2
    assert output["assets"][0]["regions"][0]["bbox_semantics"] == "text_container_region"
    assert output["assets"][1]["regions"][0]["bbox_status"] == "manually_annotated"
    assert output["assets"][1]["regions"][0]["bbox"] == {"x": 1, "y": 2, "width": 3, "height": 4}

    assert json.loads((tmp_path / "real" / "manifest.json").read_text(encoding="utf-8")) == real_before
    assert json.loads((tmp_path / "generated" / "manifest.json").read_text(encoding="utf-8")) == generated_before


def test_build_detection_ocr_ground_truth_rejects_invalid_relative_path(tmp_path):
    real_manifest = base_real_manifest()
    generated_manifest = base_generated_manifest()
    generated_manifest["assets"][0]["relative_path"] = "../synthetic_01_clean_dialogue.webp"
    prepare_sample_tree(tmp_path, real_manifest, generated_manifest)

    with pytest.raises(subprocess.CalledProcessError):
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--samples-dir", str(tmp_path)],
            cwd=ROOT_DIR,
            check=True,
        )
