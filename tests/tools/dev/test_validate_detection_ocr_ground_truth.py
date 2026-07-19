import json
import subprocess
import sys
from pathlib import Path

from PIL import Image


ROOT_DIR = Path(__file__).resolve().parents[3]
BUILDER_PATH = ROOT_DIR / "tools" / "dev" / "build_detection_ocr_ground_truth.py"
VALIDATOR_PATH = ROOT_DIR / "tools" / "dev" / "validate_detection_ocr_ground_truth.py"


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_image(path: Path, size: tuple[int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (255, 255, 255)).save(path, "WEBP")


def text_region(region_id: str, bbox: dict | None, source_type: str, core: bool = False) -> dict:
    region = {
        "region_id": region_id,
        "region_type": "dialogue_bubble",
        "bbox": bbox,
        "bbox_semantics": "text_container_region",
        "text_orientation": "vertical",
        "expected_text": "テスト 表示",
        "expected_text_lines": ["テスト", "表示"],
        "normalized_text": "テスト表示",
        "language": "ja",
    }
    if source_type == "real":
        region["include_in_core_ocr_score"] = core
        region["bbox_status"] = "manually_annotated" if core else "pending_manual_annotation"
    return region


def prepare_valid_sample_tree(tmp_path: Path) -> None:
    write_image(tmp_path / "generated" / "synthetic.webp", (40, 30))
    write_image(tmp_path / "real" / "real.webp", (50, 60))

    generated_manifest = {
        "version": "1.0",
        "assets": [
            {
                "file_name": "synthetic.webp",
                "relative_path": "generated/synthetic.webp",
                "source_type": "synthetic",
                "width": 40,
                "height": 30,
                "color_mode": "RGB",
                "scenario_tags": ["synthetic"],
                "regions": [text_region("s01_r01", {"x": 1, "y": 2, "width": 10, "height": 12}, "synthetic")],
            }
        ],
    }
    real_manifest = {
        "version": "1.0",
        "terminology": {"ground_truth": "expected output"},
        "reading_order_policy": {"page": "top_to_bottom"},
        "comparison_policy": {"core_ocr_text": "remove layout whitespace"},
        "annotation_status": {"real_assets": "core bbox ready; auxiliary pending"},
        "assets": [
            {
                "file_name": "real.webp",
                "relative_path": "real/real.webp",
                "source_type": "real",
                "width": 50,
                "height": 60,
                "color_mode": "RGB",
                "scenario_tags": ["real"],
                "regions": [
                    text_region("real_r01", {"x": 5, "y": 6, "width": 20, "height": 25}, "real", core=True),
                    text_region("real_r02", None, "real", core=False),
                ],
            }
        ],
    }
    write_json(tmp_path / "generated" / "manifest.json", generated_manifest)
    write_json(tmp_path / "real" / "manifest.json", real_manifest)
    subprocess.run([sys.executable, str(BUILDER_PATH), "--samples-dir", str(tmp_path)], cwd=ROOT_DIR, check=True)


def test_validate_detection_ocr_ground_truth_accepts_valid_tree(tmp_path):
    prepare_valid_sample_tree(tmp_path)
    real_before = (tmp_path / "real" / "manifest.json").read_bytes()
    generated_before = (tmp_path / "generated" / "manifest.json").read_bytes()

    subprocess.run([sys.executable, str(VALIDATOR_PATH), "--samples-dir", str(tmp_path)], cwd=ROOT_DIR, check=True)

    assert (tmp_path / "real" / "manifest.json").read_bytes() == real_before
    assert (tmp_path / "generated" / "manifest.json").read_bytes() == generated_before


def test_validate_detection_ocr_ground_truth_rejects_missing_real_core_bbox(tmp_path):
    prepare_valid_sample_tree(tmp_path)
    combined_path = tmp_path / "detection_ocr_ground_truth.json"
    combined = json.loads(combined_path.read_text(encoding="utf-8"))
    real_core = combined["assets"][1]["regions"][0]
    real_core["bbox"] = None
    real_core["bbox_status"] = "pending_manual_annotation"
    write_json(combined_path, combined)

    result = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), "--samples-dir", str(tmp_path)],
        cwd=ROOT_DIR,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "real core bbox_status" in result.stderr


def test_validate_detection_ocr_ground_truth_rejects_image_size_mismatch(tmp_path):
    prepare_valid_sample_tree(tmp_path)
    combined_path = tmp_path / "detection_ocr_ground_truth.json"
    combined = json.loads(combined_path.read_text(encoding="utf-8"))
    combined["assets"][0]["width"] = 41
    write_json(combined_path, combined)

    result = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), "--samples-dir", str(tmp_path)],
        cwd=ROOT_DIR,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "manifest size != image size" in result.stderr
