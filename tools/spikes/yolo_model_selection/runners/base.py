"""Shared optional-dependency and exception classification utilities."""

from __future__ import annotations

from importlib.util import find_spec


def missing_dependencies(names: tuple[str, ...]) -> list[str]:
    return [name for name in names if find_spec(name) is None]


def classify_exception(error: BaseException) -> str:
    text = f"{type(error).__name__}: {error}".lower()
    if "out of memory" in text or "cuda oom" in text:
        return "oom"
    return "runtime_error"
