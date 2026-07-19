from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image


MODULE_PATH = Path("tools/experiments/150-cleaning/materialize_page_edge_roi.py")
SPEC = importlib.util.spec_from_file_location("materialize_page_edge_roi", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
RoiMaterializationStop = MODULE.RoiMaterializationStop
materialize = MODULE.materialize
sha256 = MODULE.sha256


def _case(repo_root: Path, **updates: object) -> Path:
    source = repo_root / "data/local/sources/110-detection/sample.png"
    source.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (8, 7))
    for y in range(image.height):
        for x in range(image.width):
            image.putpixel((x, y), (x * 20, y * 20, x + y))
    image.save(source)
    payload = {
        "schema_version": "page-edge-bubble-case-v1",
        "case_id": "page_edge_bubble_test",
        "source_path": "data/local/sources/110-detection/sample.png",
        "source_sha256": sha256(source),
        "roi_xyxy": [0, 2, 5, 6],
        "purpose": "test page-edge ROI materialization",
        "algorithm_input": "full_page",
        "roi_usage": ["visualization", "annotation", "pixel_evaluation"],
    }
    payload.update(updates)
    case_path = repo_root / "data/local/datasets/150-cleaning/cases.json"
    case_path.parent.mkdir(parents=True, exist_ok=True)
    case_path.write_text(json.dumps(payload), encoding="utf-8")
    return case_path


def test_materialization_is_deterministic_and_records_full_page_input(tmp_path: Path):
    case_path = _case(tmp_path)
    first_dir = tmp_path / "data/local/runs/150-cleaning/run-1"
    second_dir = tmp_path / "data/local/runs/150-cleaning/run-2"

    first = materialize(case_path, first_dir, tmp_path)
    second = materialize(case_path, second_dir, tmp_path)

    first_roi = first_dir / "artifacts/roi.png"
    second_roi = second_dir / "artifacts/roi.png"
    assert sha256(first_roi) == sha256(second_roi)
    assert Image.open(first_roi).size == (5, 4)
    assert first["algorithm_input"] == second["algorithm_input"] == "full_page"
    assert first["artifacts"]["roi"]["role"] == "derived/visualization"


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"source_sha256": "0" * 64}, "source hash mismatch"),
        ({"roi_xyxy": [0, 2, 9, 6]}, "roi exceeds source bounds"),
        ({"algorithm_input": "crop"}, "algorithm_input must be full_page"),
    ],
)
def test_invalid_case_fails_before_creating_run(
    tmp_path: Path, updates: dict[str, object], message: str
):
    case_path = _case(tmp_path, **updates)
    run_dir = tmp_path / "data/local/runs/150-cleaning/rejected"

    with pytest.raises(RoiMaterializationStop, match=message):
        materialize(case_path, run_dir, tmp_path)

    assert not run_dir.exists()


def test_paths_cannot_escape_local_sources_or_cleaning_runs(tmp_path: Path):
    valid_case_path = _case(tmp_path)
    with pytest.raises(RoiMaterializationStop, match="run_dir must remain below"):
        materialize(valid_case_path, tmp_path / "outside-run", tmp_path)

    outside = tmp_path / "outside.png"
    Image.new("RGB", (8, 7)).save(outside)
    case_path = _case(
        tmp_path,
        source_path="outside.png",
        source_sha256=sha256(outside),
    )

    with pytest.raises(RoiMaterializationStop, match="source_path must remain below"):
        materialize(
            case_path,
            tmp_path / "data/local/runs/150-cleaning/rejected",
            tmp_path,
        )


def test_existing_run_is_never_overwritten(tmp_path: Path):
    case_path = _case(tmp_path)
    run_dir = tmp_path / "data/local/runs/150-cleaning/existing"
    materialize(case_path, run_dir, tmp_path)
    original_manifest = (run_dir / "MANIFEST.json").read_bytes()

    with pytest.raises(RoiMaterializationStop, match="run output already exists"):
        materialize(case_path, run_dir, tmp_path)

    assert (run_dir / "MANIFEST.json").read_bytes() == original_manifest
