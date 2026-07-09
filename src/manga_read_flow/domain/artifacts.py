from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactSafetyMetadata:
    is_debug: bool = False
    may_contain_original_image: bool = False
    may_contain_ocr_text: bool = False
    may_contain_translation: bool = False
    may_contain_provider_response: bool = False
    contains_secret_redacted: bool = False


@dataclass(frozen=True)
class RegisterArtifactMetadata:
    artifact_id: str
    batch_id: str | None
    page_id: str | None
    owner_type: str
    owner_id: str
    artifact_type: str
    source_stage: str
    relative_path: str
    file_hash: str
    hash_algorithm: str
    byte_size: int
    mime_type: str
    width: int | None
    height: int | None
    retention_class: str
    storage_state: str
    safety: ArtifactSafetyMetadata
    dependency_hash: str | None = None


@dataclass(frozen=True)
class ProcessingArtifactSnapshot:
    artifact_id: str
    artifact_type: str
    source_stage: str
    relative_path: str
    file_hash: str
    hash_algorithm: str
    byte_size: int
    mime_type: str
    width: int | None
    height: int | None
    retention_class: str
    storage_state: str
    is_debug: bool
    may_contain_original_image: bool
    may_contain_ocr_text: bool
    may_contain_translation: bool
    may_contain_provider_response: bool
    contains_secret_redacted: bool
    dependency_hash: str | None = None
    batch_id: str | None = None
    page_id: str | None = None
    owner_type: str | None = None
    owner_id: str | None = None


@dataclass(frozen=True)
class ArtifactIntegrityReport:
    artifact_id: str
    artifact_type: str
    expected_use: str
    observed_state: str
    integrity_status: str
    expected_hash: str | None
    observed_hash: str | None
    relative_path: str
    active_reference: str | None
    rebuildability_hint: str
    evidence_summary: str
