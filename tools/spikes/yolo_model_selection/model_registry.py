"""Validated YAML-backed local model registry. This module never loads a model."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


MODEL_REQUIRED_FIELDS = {
    "family",
    "variants",
    "task_type",
    "framework",
    "supports_bbox",
    "supports_mask",
    "config_required",
    "config_path",
    "weights",
    "default_role",
}
ASSET_REQUIRED_FIELDS = {"path", "source_url", "expected_size_bytes", "expected_sha256"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty safe relative path")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError(f"{field} must be a safe relative path: {value!r}")
    return path.as_posix()


def _resolved_under(base: Path, relative: str, field: str) -> Path:
    resolved_base = base.resolve()
    resolved = (resolved_base / relative).resolve()
    if not resolved.is_relative_to(resolved_base):
        raise ValueError(f"{field} must be a safe relative path: {relative!r}")
    return resolved


def _file_evidence(path: Path, prefix: str) -> dict[str, Any]:
    exists = path.is_file()
    return {
        f"{prefix}_exists": exists,
        f"{prefix}_size_bytes": path.stat().st_size if exists else None,
        f"{prefix}_sha256": sha256_file(path) if exists else None,
    }


def _load_assets(raw_assets: Any, weights_root_path: Path) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_assets, dict):
        raise ValueError("models config assets must be a mapping")
    assets: dict[str, dict[str, Any]] = {}
    for name, raw in raw_assets.items():
        if not isinstance(name, str) or not name or not isinstance(raw, dict):
            raise ValueError("each registry asset must have a non-empty name and mapping value")
        missing = sorted(ASSET_REQUIRED_FIELDS - raw.keys())
        if missing:
            raise ValueError(f"asset {name!r} is missing required fields: {missing}")
        relative_path = _safe_relative(raw["path"], f"assets.{name}.path")
        expected_size = raw["expected_size_bytes"]
        expected_hash = raw["expected_sha256"]
        if not isinstance(expected_size, int) or isinstance(expected_size, bool) or expected_size <= 0:
            raise ValueError(f"asset {name!r} expected_size_bytes must be a positive integer")
        if not isinstance(expected_hash, str) or len(expected_hash) != 64 or any(c not in "0123456789abcdef" for c in expected_hash):
            raise ValueError(f"asset {name!r} expected_sha256 must be a lowercase SHA-256")
        if not isinstance(raw["source_url"], str) or not raw["source_url"]:
            raise ValueError(f"asset {name!r} source_url must be a non-empty string")
        path = _resolved_under(weights_root_path, relative_path, f"assets.{name}.path")
        evidence = _file_evidence(path, "actual")
        if not evidence["actual_exists"]:
            integrity_status = "missing"
        elif evidence["actual_size_bytes"] != expected_size:
            integrity_status = "size_mismatch"
        elif evidence["actual_sha256"] != expected_hash:
            integrity_status = "hash_mismatch"
        else:
            integrity_status = "verified"
        assets[name] = {
            "path": relative_path,
            "source_url": raw["source_url"],
            "expected_size_bytes": expected_size,
            "expected_sha256": expected_hash,
            **evidence,
            "integrity_status": integrity_status,
        }
    return assets


def load_registry(models_config: Path, repo_root: Path) -> dict[str, Any]:
    """Load, validate and hash one immutable registry snapshot."""
    raw = yaml.safe_load(models_config.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("models config root must be a mapping")
    weights_root = _safe_relative(raw.get("weights_root"), "weights_root")
    weights_root_path = _resolved_under(repo_root, weights_root, "weights_root")
    assets = _load_assets(raw.get("assets", {}), weights_root_path)
    raw_models = raw.get("models")
    if not isinstance(raw_models, list) or not raw_models:
        raise ValueError("models config models must be a non-empty list")

    models: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, raw_model in enumerate(raw_models):
        if not isinstance(raw_model, dict):
            raise ValueError(f"models[{index}] must be a mapping")
        missing = sorted(MODEL_REQUIRED_FIELDS - raw_model.keys())
        if missing:
            raise ValueError(f"models[{index}] is missing required fields: {missing}")
        family = raw_model["family"]
        variants = raw_model["variants"]
        weights = raw_model["weights"]
        if not isinstance(family, str) or not family:
            raise ValueError(f"models[{index}].family must be a non-empty string")
        if not isinstance(variants, list) or not variants or not all(isinstance(item, str) and item for item in variants):
            raise ValueError(f"models[{index}].variants must be a non-empty string list")
        if not isinstance(weights, dict):
            raise ValueError(f"models[{index}].weights must be a mapping")
        for boolean_field in ("supports_bbox", "supports_mask", "config_required"):
            if not isinstance(raw_model[boolean_field], bool):
                raise ValueError(f"models[{index}].{boolean_field} must be boolean")
        for string_field in ("task_type", "framework", "default_role"):
            if not isinstance(raw_model[string_field], str) or not raw_model[string_field]:
                raise ValueError(f"models[{index}].{string_field} must be a non-empty string")

        config_path = raw_model["config_path"]
        if config_path is not None:
            config_path = _safe_relative(config_path, f"models[{index}].config_path")
        config_file = _resolved_under(weights_root_path, config_path, f"models[{index}].config_path") if config_path else None
        config_evidence = (
            _file_evidence(config_file, "config")
            if config_file is not None
            else {"config_exists": False, "config_size_bytes": None, "config_sha256": None}
        )
        asset_name = raw_model.get("text_encoder_asset")
        if asset_name is not None and asset_name not in assets:
            raise ValueError(f"model {family!r} references unknown asset {asset_name!r}")

        for variant in variants:
            key = (family, variant)
            if key in seen:
                raise ValueError(f"duplicate model family/variant: {family} {variant}")
            seen.add(key)
            if variant not in weights:
                raise ValueError(f"model {family} {variant} is missing its weight path")
            weight_path = _safe_relative(weights[variant], f"model {family} {variant} weight_path")
            weight_file = _resolved_under(weights_root_path, weight_path, f"model {family} {variant} weight_path")
            weight_evidence = _file_evidence(weight_file, "weight")
            unavailable: list[str] = []
            if not weight_evidence["weight_exists"]:
                unavailable.append("weight_missing")
            if raw_model["config_required"] and not config_evidence["config_exists"]:
                unavailable.append("config_unavailable")
            if asset_name is not None and assets[asset_name]["integrity_status"] != "verified":
                unavailable.append(f"asset_{assets[asset_name]['integrity_status']}")
            models.append(
                {
                    "family": family,
                    "variant": variant,
                    "task_type": raw_model["task_type"],
                    "framework": raw_model["framework"],
                    "weight_path": weight_path,
                    **weight_evidence,
                    "supports_bbox": raw_model["supports_bbox"],
                    "supports_mask": raw_model["supports_mask"],
                    "default_role": raw_model["default_role"],
                    "config_required": raw_model["config_required"],
                    "config_path": config_path,
                    **config_evidence,
                    "text_encoder_asset": asset_name,
                    "available": not unavailable,
                    "unavailable_reasons": unavailable,
                }
            )

    return {
        "models_config": str(models_config.resolve()),
        "repo_root": repo_root.resolve(),
        "weights_root": weights_root,
        "weights_root_path": weights_root_path,
        "assets": assets,
        "models": models,
    }


def find_model(registry_snapshot: dict[str, Any], family: str, variant: str) -> dict[str, Any]:
    for model in registry_snapshot["models"]:
        if model["family"] == family and model["variant"] == variant:
            return model
    raise KeyError(f"unregistered model: {family} {variant}")


def weight_path(registry_snapshot: dict[str, Any], model: dict[str, Any]) -> Path:
    return _resolved_under(registry_snapshot["weights_root_path"], model["weight_path"], "weight_path")


def asset_path(registry_snapshot: dict[str, Any], asset: dict[str, Any]) -> Path:
    return _resolved_under(registry_snapshot["weights_root_path"], asset["path"], "asset path")
