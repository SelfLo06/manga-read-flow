"""Best-effort local environment snapshot; missing optional packages are data, not crashes."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from .model_registry import registry
except ImportError:
    from model_registry import registry


PACKAGES = ("torch", "ultralytics", "mmengine", "mmdet", "mmcv", "mmyolo")


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def git_value(*args: str) -> str | None:
    result = subprocess.run(["git", *args], text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def nvidia_smi() -> dict[str, str | None]:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return {"name": None, "total_memory": None, "driver": None}
    fields = [item.strip() for item in result.stdout.splitlines()[0].split(",")]
    return dict(zip(("name", "total_memory", "driver"), fields, strict=False))


def build_report(data_root: Path) -> dict[str, Any]:
    versions = {name: package_version(name) for name in PACKAGES}
    torch_info: dict[str, Any] = {"version": versions["torch"], "cuda_runtime": None, "cuda_available": False}
    if versions["torch"]:
        try:
            import torch  # type: ignore[import-not-found]

            torch_info.update({"cuda_runtime": torch.version.cuda, "cuda_available": torch.cuda.is_available()})
        except Exception as error:  # optional import may fail from a broken binary install
            torch_info["import_error"] = f"{type(error).__name__}: {error}"
    return {
        "schema_version": "0.1",
        "generated_at": datetime.now(UTC).isoformat(),
        "operating_system": platform.platform(),
        "python": sys.version,
        "torch": torch_info,
        "gpu": nvidia_smi(),
        "packages": versions,
        "git": {"commit": git_value("rev-parse", "HEAD"), "branch": git_value("branch", "--show-current")},
        "models": registry(data_root),
        "missing_dependencies": sorted(name for name, version in versions.items() if version is None),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data/local"))
    parser.add_argument("--output", type=Path, default=Path("data/local/yolo-model-selection/environment.json"))
    args = parser.parse_args()
    report = build_report(args.data_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote environment snapshot to {args.output}")


if __name__ == "__main__":
    main()

