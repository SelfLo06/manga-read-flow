#!/usr/bin/env python3
"""Freeze the maintainer-accepted black2 oracle without changing its candidate."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
CANDIDATE = ROOT / "data/local/datasets/150-cleaning/page-edge-bubble-v0.1/oracles/black2_touching_bubbles_001/candidate-v0.1"
ACCEPTED = CANDIDATE.parent / "accepted-v1"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def freeze() -> Path:
    if ACCEPTED.exists():
        raise RuntimeError(f"accepted oracle already exists: {ACCEPTED}")
    cases = json.loads((CANDIDATE / "cases.json").read_text(encoding="utf-8"))
    source = ROOT / cases["source_path"]
    if not source.is_file() or digest(source) != cases["source_sha256"]:
        raise RuntimeError("black2 source hash mismatch")
    shutil.copytree(CANDIDATE, ACCEPTED)
    association_path = ACCEPTED / "association.json"
    association = json.loads(association_path.read_text(encoding="utf-8"))
    association["status"] = "human_reviewed_accepted"
    association["review"] = {
        "reviewer": "maintainer decision",
        "decision": "ACCEPTED_V1",
        "notes": "Two touching BubbleInstances remain semantically distinct; merge is forbidden."
    }
    write_json(association_path, association)
    validation_path = ACCEPTED / "VALIDATION.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    validation["status"] = "human_reviewed_accepted"
    validation["reviewer"] = "maintainer decision"
    write_json(validation_path, validation)
    (ACCEPTED / "README.md").write_text(
        "# black2 touching bubbles accepted oracle v1\n\n"
        "Status: `human_reviewed_accepted`. Maintainer decision: two touching BubbleInstances are semantically distinct; merging is forbidden. Semantic masks are evaluation-only.\n",
        encoding="utf-8",
    )
    records = []
    for path in sorted(item for item in ACCEPTED.rglob("*") if item.is_file() and item.name != "ORACLE_MANIFEST.json"):
        records.append({"path": path.relative_to(ACCEPTED).as_posix(), "sha256": digest(path), "role": "accepted_oracle_or_reference"})
    manifest = {
        "schema_version": "oracle-manifest-v3",
        "case_id": cases["case_id"],
        "oracle_version": "accepted-v1",
        "status": "human_reviewed_accepted",
        "reviewer": "maintainer decision",
        "source_sha256": cases["source_sha256"],
        "roi_xyxy": cases["roi_xyxy"],
        "coordinate_space": "roi_local",
        "files": records,
    }
    write_json(ACCEPTED / "ORACLE_MANIFEST.json", manifest)
    return ACCEPTED


if __name__ == "__main__":
    print(freeze())
