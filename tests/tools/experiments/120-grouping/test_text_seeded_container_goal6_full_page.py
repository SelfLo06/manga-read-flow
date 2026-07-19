from __future__ import annotations

import hashlib
import json

import numpy as np
from PIL import Image

from tools.experiments.grouping_120.text_seeded_container_association import goal6_full_page_trial as full_page
from tools.experiments.grouping_120.text_seeded_container_association import goal6_mask_harness as mask


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_materialize_copies_only_the_two_approved_pages(tmp_path, monkeypatch):
    source_dir = tmp_path / "data" / "local" / "sources" / "110-detection" / "real-samples-v0.1"
    source_dir.mkdir(parents=True)
    Image.new("RGB", (7, 5), "white").save(source_dir / "black2.webp")
    Image.new("RGB", (6, 4), "black").save(source_dir / "gura_color.webp")
    monkeypatch.setattr(full_page, "ROOT", tmp_path)

    output = tmp_path / "output"
    full_page.materialize(output)

    spec = json.loads((output / "S1-INPUT-SPEC.local.json").read_text(encoding="utf-8"))
    assert [item["asset_id"] for item in spec["assets"]] == ["case-71", "case-72"]
    manifest = json.loads((output / "FULL-PAGE-SOURCE-MANIFEST.local.json").read_text(encoding="utf-8"))
    for item in manifest["approved_user_sources"]:
        copied = output / "images" / f"{item['asset_id']}.webp"
        assert item["source_sha256"] == item["copied_sha256"] == _sha256(copied)


def test_comparison_is_four_full_page_panels():
    source = np.zeros((3, 5, 3), dtype=np.uint8)
    rendered = full_page.comparison(source, source, source, source)
    assert rendered.size == (20, 3)


def test_union_effective_can_show_applied_and_skipped_risks_separately():
    empty = np.zeros((3, 4), dtype=np.bool_)
    e1 = empty.copy()
    e1[0, 0] = True
    e3 = empty.copy()
    e3[2, 3] = True

    def result(context_id, risk, decision, effective):
        return mask.ContextResult(
            context_id, {}, empty, empty, empty, empty, empty, empty, effective,
            risk, decision, {},
        )

    results = (result("e1", "E1", "REVIEW_REQUIRED", e1), result("e3", "E3", "SKIP", e3))
    assert np.array_equal(full_page.union_effective(results, {"E1"}), e1)
    assert np.array_equal(full_page.union_effective(results, {"E1", "E2"}), e1)
    assert np.array_equal(full_page.union_effective(results, {"E3"}), e3)
