"""Small, dependency-free helpers for spike result records."""

from __future__ import annotations

from typing import Any


STATUSES = {
    "success",
    "empty_result",
    "dependency_missing",
    "model_load_failed",
    "invalid_output",
    "oom",
    "runtime_error",
}


def error_result(
    *,
    run_id: str,
    sample_id: str,
    model: dict[str, Any],
    request: dict[str, Any],
    status: str,
    message: str,
    missing_dependencies: list[str] | None = None,
) -> dict[str, Any]:
    """Create a normalized failure record without importing model libraries."""
    if status not in STATUSES - {"success", "empty_result"}:
        raise ValueError(f"unsupported error status: {status}")
    error: dict[str, Any] = {"message": message}
    if missing_dependencies:
        error["missing_dependencies"] = sorted(missing_dependencies)
    return {
        "schema_version": "0.1",
        "run_id": run_id,
        "sample_id": sample_id,
        "model": model,
        "request": request,
        "actual": {"input_width": 0, "input_height": 0, "processed_width": 0, "processed_height": 0},
        "detections": [],
        "timing": {},
        "gpu": {},
        "status": status,
        "error": error,
    }
