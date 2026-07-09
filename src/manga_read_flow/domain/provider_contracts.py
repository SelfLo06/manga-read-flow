from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol


class ProviderOutcome(str, Enum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    REFUSAL = "refusal"
    INVALID_OUTPUT = "invalid_output"


@dataclass(frozen=True)
class ProviderError:
    kind: str
    code: str
    sanitized_message: str
    is_provider_refusal: bool = False


@dataclass(frozen=True)
class ProviderRequest:
    request_id: str
    stage: str
    target_type: str
    target_id: str
    page_id: str
    text_block_ids: tuple[str, ...]
    attempt_temp_root: Path
    input_hash: str
    config_hash: str
    context_hash: str
    source_language: str
    target_language: str
    inputs: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderTempFileRef:
    temp_ref_id: str
    kind: str
    temp_path: Path
    media_type: str | None = None
    expected_artifact_type: str | None = None
    safety_flags: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResult:
    outcome: ProviderOutcome
    provider_name: str
    model_id: str | None = None
    payload: dict[str, object] = field(default_factory=dict)
    error: ProviderError | None = None
    temp_files: tuple[ProviderTempFileRef, ...] = ()


@dataclass(frozen=True)
class ProviderIdentity:
    provider_name: str
    provider_kind: str
    model_id: str | None
    tool_name: str
    tool_version: str


class StageProvider(Protocol):
    identity: ProviderIdentity

    def run(self, request: ProviderRequest) -> ProviderResult:
        ...
