import json
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT_DIR / "tools" / "dev" / "generate_synthetic_samples.py"


def test_generate_synthetic_samples_creates_assets_and_manifest(tmp_path):
    output_dir = tmp_path / "synthetic"
    output_dir.mkdir()
    extra_file = output_dir / "keep_me.txt"
    extra_file.write_text("not owned by generator", encoding="utf-8")

    command = [sys.executable, str(SCRIPT_PATH), "--output-dir", str(output_dir)]
    subprocess.run(command, cwd=ROOT_DIR, check=True)
    subprocess.run(command, cwd=ROOT_DIR, check=True)

    expected_files = {
        "synthetic_01_clean_dialogue.webp",
        "synthetic_02_narration_boxes.webp",
        "synthetic_03_small_bubble_overflow.webp",
        "synthetic_04_complex_background_skip.webp",
    }

    generated_files = {path.name for path in output_dir.glob("*.webp")}
    assert generated_files == expected_files

    manifest_path = output_dir / "manifest.json"
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["version"]
    assert manifest["generated_at"]
    assert len(manifest["assets"]) == 4

    actual_files = {path.name for path in output_dir.iterdir() if path.is_file()}
    assert extra_file.name in actual_files
    region_types = set()
    intended_uses = set()

    for asset in manifest["assets"]:
        assert asset["file_name"] in expected_files
        assert asset["relative_path"] == f"{output_dir.name}/{asset['file_name']}"
        assert asset["source_type"] == "synthetic"
        assert asset["file_name"] in actual_files
        assert asset["width"] > 0
        assert asset["height"] > 0
        assert asset["color_mode"]
        assert asset["scenario_tags"]
        assert asset["regions"]

        for region in asset["regions"]:
            assert region["region_type"] in {
                "dialogue_bubble",
                "narration_box",
                "difficult_text",
            }
            assert region["bbox_semantics"] == "text_container_region"
            assert region["expected_text"]
            assert region["expected_text_lines"] == [region["expected_text"]]
            assert region["normalized_text"] == region["expected_text"]
            assert region["language"] == "ja"
            assert region["text_orientation"] in {"horizontal", "vertical", "angled"}
            assert region["expected_difficulty"] in {"easy", "medium", "hard"}
            assert region["intended_use"] in {
                "detection",
                "ocr",
                "overflow_risk",
                "skip_risk",
            }

            bbox = region["bbox"]
            assert bbox["x"] >= 0
            assert bbox["y"] >= 0
            assert bbox["width"] > 0
            assert bbox["height"] > 0

            region_types.add(region["region_type"])
            intended_uses.add(region["intended_use"])

    assert "dialogue_bubble" in region_types
    assert "narration_box" in region_types
    assert "overflow_risk" in intended_uses
    assert "skip_risk" in intended_uses
