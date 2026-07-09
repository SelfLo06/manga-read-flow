from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


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
class ProviderResult:
    outcome: ProviderOutcome
    provider_name: str
    model_id: str | None = None
    payload: dict[str, object] = field(default_factory=dict)
    error: ProviderError | None = None
