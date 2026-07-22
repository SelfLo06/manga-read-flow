from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any


DETECTION_EVIDENCE_SCHEMA_VERSION = "accepted-detection-evidence-set.v1"
DETECTION_DEPENDENCY_ID_PREFIX = "detection-set-v1:"


@dataclass(frozen=True)
class StableDetectionProviderIdentity:
    provider_name: str
    provider_kind: str
    model_id: str | None
    tool_name: str
    tool_version: str


@dataclass(frozen=True)
class AcceptedDetectionEvidenceMember:
    text_block_id: str
    project_id: str
    page_id: str
    reading_order: int
    bbox_json: str
    polygon_json: str
    geometry_hash: str
    coordinate_space_json: str
    detection_provider: str
    detection_confidence: float | None
    detection_status: str = "done"


@dataclass(frozen=True)
class AcceptedDetectionEvidenceSemanticInput:
    project_id: str
    page_id: str
    source_artifact_id: str
    source_sha256: str
    coordinate_space_json: str
    detection_config_hash: str
    provider: StableDetectionProviderIdentity
    members: tuple[AcceptedDetectionEvidenceMember, ...]
    schema_version: str = DETECTION_EVIDENCE_SCHEMA_VERSION


@dataclass(frozen=True)
class CanonicalDetectionEvidenceManifest:
    detection_dependency_id: str
    canonical_manifest_sha256: str
    canonical_bytes: bytes
    schema_version: str
    project_id: str
    page_id: str
    source_artifact_id: str
    source_sha256: str
    coordinate_space_json: str
    member_ids: tuple[str, ...]


@dataclass(frozen=True)
class DetectionEvidenceAcceptanceProvenanceDraft:
    acceptance_id: str
    workflow_attempt_id: str
    workflow_decision_id: str
    provider_execution_reference: str | None


@dataclass(frozen=True)
class AcceptedDetectionEvidenceSetDraft:
    detection_dependency_id: str
    project_id: str
    page_id: str
    source_artifact_id: str
    source_sha256: str
    coordinate_space_json: str
    canonical_member_count: int
    manifest_artifact_id: str
    canonical_manifest_sha256: str
    schema_version: str
    member_ids: tuple[str, ...]
    provenance: DetectionEvidenceAcceptanceProvenanceDraft


def canonicalize_detection_evidence(
    semantic_input: AcceptedDetectionEvidenceSemanticInput,
) -> CanonicalDetectionEvidenceManifest:
    _require_nonempty("project_id", semantic_input.project_id)
    _require_nonempty("page_id", semantic_input.page_id)
    _require_nonempty("source_artifact_id", semantic_input.source_artifact_id)
    _require_sha256("source_sha256", semantic_input.source_sha256)
    _require_sha256("detection_config_hash", semantic_input.detection_config_hash)
    _require_nonempty("schema_version", semantic_input.schema_version)
    _validate_provider(semantic_input.provider)

    coordinate_space = _parse_json_object(
        "coordinate_space_json", semantic_input.coordinate_space_json
    )
    members = sorted(
        semantic_input.members,
        key=lambda member: (
            member.project_id.encode("utf-8"),
            member.page_id.encode("utf-8"),
            member.text_block_id.encode("utf-8"),
        ),
    )
    stable_ids: set[tuple[str, str, str]] = set()
    canonical_members = []
    for member in members:
        stable_id = (member.project_id, member.page_id, member.text_block_id)
        if stable_id in stable_ids:
            raise ValueError("Duplicate Detection evidence member identity.")
        stable_ids.add(stable_id)
        canonical_members.append(
            _canonical_member(
                member,
                expected_project_id=semantic_input.project_id,
                expected_page_id=semantic_input.page_id,
                expected_coordinate_space=coordinate_space,
                expected_provider=semantic_input.provider.provider_name,
            )
        )

    manifest = {
        "coordinate_space": coordinate_space,
        "detection_configuration": {
            "config_hash": semantic_input.detection_config_hash,
        },
        "member_count": len(canonical_members),
        "members": canonical_members,
        "page_id": semantic_input.page_id,
        "project_id": semantic_input.project_id,
        "provider_implementation": {
            "model_id": semantic_input.provider.model_id,
            "provider_kind": semantic_input.provider.provider_kind,
            "provider_name": semantic_input.provider.provider_name,
            "tool_name": semantic_input.provider.tool_name,
            "tool_version": semantic_input.provider.tool_version,
        },
        "schema_version": semantic_input.schema_version,
        "source_artifact_id": semantic_input.source_artifact_id,
        "source_sha256": semantic_input.source_sha256,
    }
    _validate_json_value(manifest)
    canonical_bytes = json.dumps(
        manifest,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    manifest_hash = sha256(canonical_bytes).hexdigest()
    return CanonicalDetectionEvidenceManifest(
        detection_dependency_id=f"{DETECTION_DEPENDENCY_ID_PREFIX}{manifest_hash}",
        canonical_manifest_sha256=manifest_hash,
        canonical_bytes=canonical_bytes,
        schema_version=semantic_input.schema_version,
        project_id=semantic_input.project_id,
        page_id=semantic_input.page_id,
        source_artifact_id=semantic_input.source_artifact_id,
        source_sha256=semantic_input.source_sha256,
        coordinate_space_json=json.dumps(
            coordinate_space,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        member_ids=tuple(member.text_block_id for member in members),
    )


def _canonical_member(
    member: AcceptedDetectionEvidenceMember,
    *,
    expected_project_id: str,
    expected_page_id: str,
    expected_coordinate_space: dict[str, Any],
    expected_provider: str,
) -> dict[str, Any]:
    _require_nonempty("text_block_id", member.text_block_id)
    if member.project_id != expected_project_id or member.page_id != expected_page_id:
        raise ValueError("Detection evidence member project/page binding is invalid.")
    if member.reading_order < 0:
        raise ValueError("Detection evidence reading_order must be non-negative.")
    _require_sha256("geometry_hash", member.geometry_hash)
    if member.detection_status != "done":
        raise ValueError("Detection evidence member must be formally accepted.")
    if member.detection_provider != expected_provider:
        raise ValueError("Detection evidence provider binding is inconsistent.")
    if member.detection_confidence is not None and not math.isfinite(
        member.detection_confidence
    ):
        raise ValueError("Detection evidence confidence must be finite.")

    bbox = _parse_json_object("bbox_json", member.bbox_json)
    polygon = _parse_json_value("polygon_json", member.polygon_json)
    coordinate_space = _parse_json_object(
        "member.coordinate_space_json", member.coordinate_space_json
    )
    if coordinate_space != expected_coordinate_space:
        raise ValueError("Detection evidence coordinate-space binding is inconsistent.")
    return {
        "bbox": bbox,
        "coordinate_space": coordinate_space,
        "detection_confidence": member.detection_confidence,
        "detection_provider": member.detection_provider,
        "detection_status": member.detection_status,
        "geometry_hash": member.geometry_hash,
        "page_id": member.page_id,
        "polygon": polygon,
        "project_id": member.project_id,
        "reading_order": member.reading_order,
        "text_block_id": member.text_block_id,
    }


def _parse_json_object(name: str, payload: str) -> dict[str, Any]:
    value = _parse_json_value(name, payload)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object.")
    return value


def _parse_json_value(name: str, payload: str) -> Any:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} must contain valid JSON.") from exc
    _validate_json_value(value)
    return value


def _validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Canonical Detection evidence only accepts finite numbers.")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Canonical Detection evidence keys must be strings.")
            _validate_json_value(item)
        return
    raise ValueError(f"Unsupported canonical Detection evidence value: {type(value)!r}")


def _validate_provider(provider: StableDetectionProviderIdentity) -> None:
    _require_nonempty("provider_name", provider.provider_name)
    _require_nonempty("provider_kind", provider.provider_kind)
    _require_nonempty("tool_name", provider.tool_name)
    _require_nonempty("tool_version", provider.tool_version)


def _require_nonempty(name: str, value: str) -> None:
    if not value:
        raise ValueError(f"{name} must not be empty.")


def _require_sha256(name: str, value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest.")
