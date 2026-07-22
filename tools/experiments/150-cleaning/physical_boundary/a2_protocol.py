"""Freeze and sealed-holdout guards for the A2 experiment."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_freeze(freeze_path: Path, producer_path: Path, config_hash: str) -> dict:
    if not freeze_path.is_file():
        raise ValueError("valid FREEZE.json is required before holdout production")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    required = {"producer_implementation_sha256", "config_sha256", "candidate_schema_sha256", "evaluator_sha256"}
    if not required <= freeze.keys():
        raise ValueError("FREEZE.json is incomplete")
    if sha256(producer_path) != freeze["producer_implementation_sha256"]:
        raise ValueError("producer hash does not match freeze")
    if config_hash != freeze["config_sha256"]:
        raise ValueError("config hash does not match freeze")
    return freeze
