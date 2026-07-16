"""Run-local output layout with deliberate no-overwrite semantics."""

from __future__ import annotations

from pathlib import Path


RUN_CHILDREN = ("raw", "normalized", "overlays", "masks", "crops", "logs")


def validate_run_id(run_id: str) -> str:
    if not run_id or run_id in {".", ".."} or any(char in run_id for char in "/\\"):
        raise ValueError("run_id must be a non-empty path component")
    return run_id


def create_run_layout(output_root: Path, run_id: str) -> Path:
    run_dir = output_root / "runs" / validate_run_id(run_id)
    if run_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {run_dir}")
    run_dir.mkdir(parents=True)
    for child in RUN_CHILDREN:
        (run_dir / child).mkdir()
    return run_dir
