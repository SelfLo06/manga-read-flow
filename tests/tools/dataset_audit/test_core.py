from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from tools.dataset_audit.core import (
    AuditConfig,
    classify_variant_dirs,
    natural_key,
    pair_pages_monotonic,
    _classify_work,
    _split_proposal,
    validate_output_consistency,
    run_audit,
)


def _write_image(path: Path, color: int, size: tuple[int, int] = (80, 120)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("L", size, color=color).save(path)


def test_natural_key_orders_unicode_numbered_names() -> None:
    names = ["p10.png", "p2.png", "第3頁.png", "第1頁.png"]
    assert sorted(names, key=natural_key) == ["p2.png", "p10.png", "第1頁.png", "第3頁.png"]


def test_variant_identification_handles_chinese_and_textless_markers(tmp_path: Path) -> None:
    work = tmp_path / "作品"
    for name in ("作品", "作品 [無字]", "作品 [中国翻訳]"):
        (work / name).mkdir(parents=True)
    roles, issues = classify_variant_dirs(work)
    assert issues == []
    assert roles["original_jp"].name == "作品"
    assert roles["textless_reference"].name.endswith("[無字]")
    assert roles["chinese_reference"].name.endswith("[中国翻訳]")


def test_monotonic_pairing_keeps_extra_reference_page_unmatched() -> None:
    anchors = ["a", "b"]
    references = ["cover", "a", "b"]
    score = {
        ("a", "cover"): 0.0,
        ("a", "a"): 0.98,
        ("a", "b"): 0.05,
        ("b", "cover"): 0.0,
        ("b", "a"): 0.05,
        ("b", "b"): 0.97,
    }
    result = pair_pages_monotonic(anchors, references, lambda a, b: score[(a, b)])
    assert result.matches == {"a": "a", "b": "b"}
    assert result.extra_references == ["cover"]


def test_audit_records_decode_failure_and_is_resumable(tmp_path: Path) -> None:
    root = tmp_path / "data"
    work = root / "作品"
    for variant in ("作品", "作品 [無字]", "作品 [中国翻訳]"):
        _write_image(work / variant / "01.png", 230)
    (work / "作品" / "broken.jpg").write_bytes(b"not-an-image")
    (work / "作品" / "notes.txt").write_text("metadata", encoding="utf-8")

    output = tmp_path / "output"
    cache = tmp_path / "cache"
    config = AuditConfig(input_root=root, output_dir=output, cache_dir=cache)
    first = run_audit(config)
    second = run_audit(config)

    assert first["coverage"]["total_input_files"] == 5
    assert first["coverage"]["successfully_processed_files"] == 3
    assert first["coverage"]["explicitly_failed_files"] == 1
    assert first["coverage"]["unsupported_non_image_files"] == 1
    assert second["cache_reused_files"] >= 3
    records = [json.loads(line) for line in (output / "file-inventory.jsonl").read_text().splitlines()]
    assert {record["decode_status"] for record in records} >= {"processed", "decode_failed", "unsupported_non_image"}


def test_source_hash_change_invalidates_cache(tmp_path: Path) -> None:
    root = tmp_path / "data"
    work = root / "作品"
    for variant in ("作品", "作品 [無字]", "作品 [中国翻訳]"):
        _write_image(work / variant / "01.png", 230)
    config = AuditConfig(input_root=root, output_dir=tmp_path / "out", cache_dir=tmp_path / "cache")
    first = run_audit(config)
    _write_image(work / "作品" / "01.png", 20)
    second = run_audit(config)
    assert first["input_file_sha256_tree_before"] != second["input_file_sha256_tree_before"]
    assert second["cache_reused_files"] == 2


def test_work_medium_uses_page_ratio_not_a_single_color_cover() -> None:
    base_metrics = {"edge_density": .1, "screentone_indicator": .1, "dense_text_ratio": .1, "noise_estimate": .01, "vertical_orientation_estimate": 1, "panel_layout_density": .2}
    records = [{"work_id": "work-001", "decode_status": "processed", "width": 100, "height": 100, "metrics": {**base_metrics, "medium": "grayscale"}} for _ in range(9)]
    records.append({"work_id": "work-001", "decode_status": "processed", "width": 100, "height": 100, "metrics": {**base_metrics, "medium": "color"}})
    row = _classify_work(records, [], {"work-001": "test"})[0]
    assert row["medium"] == "mostly_grayscale"
    assert row["grayscale_page_ratio"] == .9
    assert row["e_class_estimate"] == "unavailable_without_detector"
    assert row["text_orientation_label"] == "proxy_only"
    assert row["layout_complexity_label"] == "proxy_only"
    assert "text_orientation" not in row and "layout_complexity" not in row


def test_split_keeps_manual_series_group_together() -> None:
    rows = [{"work_id": work, "confidence": "low", "jp_textless_pairing_quality": "high", "triplet_qualification_summary": "mostly_silver"} for work in ("work-001", "work-002", "work-006", "work-003")]
    split = _split_proposal(rows, {"work-001": "series-alpha", "work-002": "series-alpha", "work-006": "series-alpha"})
    assert {split["work_reasons"][work]["partition"] for work in ("work-001", "work-002", "work-006")} == {"Dev"}


def test_cross_output_extra_reference_consistency(tmp_path: Path) -> None:
    (tmp_path / "manual-review.csv").write_text("item_type,relative_path\nextra_reference_page,a/x.png\nextra_reference_page,b/x.png\n" + "pairing_unresolved,x\n" * 3 + "registration_low_confidence,x\n" * 12, encoding="utf-8")
    (tmp_path / "variant-summary.csv").write_text("extra_reference_pages\n1\n1\n", encoding="utf-8")
    validate_output_consistency(tmp_path)
