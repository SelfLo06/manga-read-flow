from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from tools.experiments.grouping_120.text_seeded_container_association import goal6_materialize_supplement as supplement


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _selection(root: Path, *, duplicate_source: bool = False) -> Path:
    assets = []
    for index in range(6):
        source = root / "data" / "local" / f"source-{index}.png"
        source.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (40, 30), (255, index, 0)).save(source)
        selected = root / "data" / "local" / "source-0.png" if duplicate_source and index == 5 else source
        assets.append(
            {
                "asset_id": f"cal-{61 + index}",
                "target_class": "test-only",
                "source_relative_path": selected.relative_to(root).as_posix(),
                "source_sha256": _sha256(selected),
                "crop_xywh": [3, 4, 20, 15],
            }
        )
    selection = root / "selection.json"
    selection.write_text(
        json.dumps({"schema_version": supplement.SCHEMA, "assets": assets}), encoding="utf-8"
    )
    return selection


def test_materialize_preserves_sources_and_writes_a_hash_locked_s1_spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(supplement, "ROOT", tmp_path)
    selection = _selection(tmp_path)
    before = _sha256(tmp_path / "data" / "local" / "source-0.png")

    result = supplement.materialize(selection, tmp_path / "out")

    spec = json.loads((tmp_path / "out" / "S1-INPUT-SPEC.local.json").read_text(encoding="utf-8"))
    assert result["asset_count"] == 6
    assert result["source_hash_count"] == 6
    assert [item["asset_id"] for item in spec["assets"]] == [f"cal-{61 + index}" for index in range(6)]
    assert all((tmp_path / "out" / item["relative_path"]).is_file() for item in spec["assets"])
    assert all((item["width"], item["height"]) == (20, 15) for item in spec["assets"])
    assert _sha256(tmp_path / "data" / "local" / "source-0.png") == before


def test_materialize_rejects_a_reused_source_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(supplement, "ROOT", tmp_path)
    selection = _selection(tmp_path, duplicate_source=True)

    with pytest.raises(supplement.SupplementStop, match="one source page"):
        supplement.materialize(selection, tmp_path / "out")
