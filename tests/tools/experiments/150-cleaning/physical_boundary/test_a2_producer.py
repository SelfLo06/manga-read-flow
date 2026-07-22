from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import cv2
import numpy as np
import pytest
from PIL import Image


ROOT = Path("tools/experiments/150-cleaning/physical_boundary")


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PRODUCER = _load("physical_boundary_a2_producer", "a2_producer.py")
EVALUATOR = _load("physical_boundary_a2_evaluator", "a2_evaluator.py")
PROTOCOL = _load("physical_boundary_a2_protocol", "a2_protocol.py")


def _fixture(tmp_path: Path, groups=(("g1", (20, 20, 32, 42)), ("g2", (38, 20, 50, 42)))):
    image = np.full((80, 100, 3), 245, dtype=np.uint8)
    cv2.ellipse(image, (35, 31), (27, 20), 0, 0, 360, (20, 20, 20), 2)
    source = tmp_path / "source.png"
    Image.fromarray(image).save(source)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    text_groups = []
    for group_id, (x0, y0, x1, y1) in groups:
        text_groups.append({"text_group_id": group_id, "fragment_ids": [group_id + "-f"], "fragment_geometries": [{"fragment_id": group_id + "-f", "geometry_type": "polygon", "points": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}]})
    payload = {"case_id": "synthetic", "split": "development", "source": {"filename": source.name, "sha256": source_hash, "width": 100, "height": 80}, "coordinate_space": {"origin": "top-left", "unit": "pixel", "x_range": [0, 99], "y_range": [0, 79]}, "grouping_input": {"kind": "experimental_frozen_grouping", "manifest_id": "m", "manifest_sha256": "0" * 64, "text_groups": text_groups}, "capability_tags": ["SYNTHETIC"], "support_scope": "M1_SUPPORTED"}
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    return source, input_path


def test_oracle_free_producer_preserves_group_identity_and_text_safe_separator(tmp_path):
    source, input_path = _fixture(tmp_path)
    candidate, _ = PRODUCER.produce(source, input_path)
    assert [item["text_group_ids"] for item in candidate["instances"]] == [["g1"], ["g2"]]
    assert all(len(item["text_group_ids"]) == 1 for item in candidate["instances"])
    masks = []
    for instance in candidate["instances"]:
        mask = np.zeros((80, 100), dtype=np.uint8)
        cv2.fillPoly(mask, [np.asarray(instance["interior"]["points"], dtype=np.int32)], 1)
        masks.append(mask.astype(bool))
    assert not np.any(masks[0] & masks[1])
    assert not (tmp_path / "oracle.geojson").exists()
    for relation in candidate["relations"]:
        if relation["separator"]:
            assert relation["separator"]["evidence"] == "VIRTUAL"


def test_no_legal_separator_stays_unresolved_and_incomplete(tmp_path):
    source, input_path = _fixture(tmp_path, groups=(("g1", (20, 10, 45, 60)), ("g2", (42, 10, 67, 60))))
    candidate, _ = PRODUCER.produce(source, input_path, PRODUCER.ProducerConfig(text_exclusion_margin=18))
    assert candidate["relations"]
    assert any(item["resolution"] == "UNRESOLVED" and item["separator"] is None for item in candidate["relations"])
    assert candidate["candidate_disposition"] == "INCOMPLETE"


def test_page_edge_closure_is_virtual_and_exactly_on_edge(tmp_path):
    source, input_path = _fixture(tmp_path, groups=(("g1", (0, 20, 15, 45)),))
    candidate, _ = PRODUCER.produce(source, input_path)
    instance = candidate["instances"][0]
    assert "LEFT" in instance["page_truncation_directions"]
    closure = next(item for item in instance["closures"] if item["direction"] == "LEFT")
    assert closure["evidence"] == "VIRTUAL"
    assert all(point[0] == 0 for point in closure["points"])
    assert instance["observed_boundary"]["evidence"] == "OBSERVED"


def test_unknown_is_not_promoted_and_panel_is_not_a_bubble_boundary(tmp_path):
    source, input_path = _fixture(tmp_path, groups=(("g1", (70, 55, 80, 65)),))
    candidate, _ = PRODUCER.produce(source, input_path, PRODUCER.ProducerConfig(boundary_support_threshold=1.0))
    instance = candidate["instances"][0]
    assert instance["resolution"] == "INCOMPLETE"
    assert instance["interior"]["evidence"] == "UNKNOWN"
    assert candidate["panel_boundary_proposals"] == []
    assert all(item["kind"] != "PANEL_BOUNDARY" for item in candidate["typed_boundaries"])


def test_evaluator_requires_frozen_candidate_and_is_read_only(tmp_path):
    source, input_path = _fixture(tmp_path, groups=(("g1", (20, 20, 32, 42)),))
    candidate, provenance = PRODUCER.produce(source, input_path)
    candidate_dir = tmp_path / "candidate"
    PRODUCER.write_candidate(candidate_dir, candidate, provenance)
    oracle = tmp_path / "oracle.geojson"
    oracle.write_text(json.dumps({"type": "FeatureCollection", "properties": {"case_id": "synthetic", "annotation_version": "1"}, "features": [{"type": "Feature", "id": "i", "properties": {"kind": "INSTANCE_INTERIOR", "status": "SUPPORTED", "evidence": "INFERRED", "instance_id": "i1", "text_group_ids": ["g1"]}, "geometry": {"type": "Polygon", "coordinates": [[[10, 10], [50, 10], [50, 60], [10, 60], [10, 10]]]}}]}), encoding="utf-8")
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({"hard_failures": ["CROSS_GROUP_MERGE"]}), encoding="utf-8")
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (candidate_dir / "candidate.json", oracle)}
    result = EVALUATOR.evaluate(candidate_dir, oracle, contract)
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before}
    assert result["candidate_sha256"]
    assert "boundary_tolerance_precision" in result["metrics"]["instances"][0]
    assert "panel_bubble_confusion" in result["metrics"]
    assert (candidate_dir / candidate["instances"][0]["interior"]["mask_ref"]).is_file()
    assert before == after
    (candidate_dir / "candidate.sha256").unlink()
    with pytest.raises(ValueError, match="not hash-frozen"):
        EVALUATOR.evaluate(candidate_dir, oracle, contract)


def test_evaluator_rejects_tampered_derived_mask_and_renders_overlay(tmp_path):
    source, input_path = _fixture(tmp_path, groups=(("g1", (20, 20, 32, 42)),))
    candidate, provenance = PRODUCER.produce(source, input_path)
    candidate_dir = tmp_path / "candidate"
    PRODUCER.write_candidate(candidate_dir, candidate, provenance)
    oracle = tmp_path / "oracle.geojson"
    oracle.write_text(json.dumps({"type": "FeatureCollection", "properties": {"case_id": "synthetic", "annotation_version": "1"}, "features": [{"type": "Feature", "id": "i", "properties": {"kind": "INSTANCE_INTERIOR", "status": "SUPPORTED", "evidence": "INFERRED", "instance_id": "i1", "text_group_ids": ["g1"]}, "geometry": {"type": "Polygon", "coordinates": [[[10, 10], [50, 10], [50, 60], [10, 60], [10, 10]]]}}, {"type": "Feature", "id": "b", "properties": {"kind": "BUBBLE_BOUNDARY", "status": "SUPPORTED", "evidence": "OBSERVED", "instance_id": "i1"}, "geometry": {"type": "LineString", "coordinates": [[10, 10], [50, 10], [50, 60], [10, 60], [10, 10]]}}]}), encoding="utf-8")
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({"hard_failures": []}), encoding="utf-8")
    overlay = tmp_path / "overlay.png"
    EVALUATOR.render_overlay(source, candidate_dir, oracle, overlay)
    assert overlay.is_file() and overlay.stat().st_size > 0
    mask_path = candidate_dir / candidate["instances"][0]["interior"]["mask_ref"]
    mask_path.write_bytes(mask_path.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="mask missing or hash mismatch"):
        EVALUATOR.evaluate(candidate_dir, oracle, contract)


def test_holdout_requires_complete_matching_freeze(tmp_path):
    producer = tmp_path / "producer.py"
    producer.write_text("pass\n", encoding="utf-8")
    with pytest.raises(ValueError, match="FREEZE"):
        PROTOCOL.verify_freeze(tmp_path / "FREEZE.json", producer, "c" * 64)
    freeze = tmp_path / "FREEZE.json"
    freeze.write_text(json.dumps({"producer_implementation_sha256": hashlib.sha256(producer.read_bytes()).hexdigest(), "config_sha256": "c" * 64, "candidate_schema_sha256": "s" * 64, "evaluator_sha256": "e" * 64}), encoding="utf-8")
    assert PROTOCOL.verify_freeze(freeze, producer, "c" * 64)
    producer.write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="producer hash"):
        PROTOCOL.verify_freeze(freeze, producer, "c" * 64)
