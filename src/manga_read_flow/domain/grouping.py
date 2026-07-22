from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any, Protocol


GROUPING_MANIFEST_SCHEMA_VERSION = "frozen-grouping-evidence-manifest.v1"
GROUPING_SNAPSHOT_ID_PREFIX = "grouping-snapshot-v1:"
GROUPING_OUTCOME_SUCCEEDED = "SUCCEEDED"
GROUPING_OUTCOME_ABSTAINED = "ABSTAINED"
GROUPING_OUTCOME_FAILED = "FAILED"
GROUPING_DISPOSITION_PRODUCED = "PRODUCED"
GROUPING_DISPOSITION_INCOMPLETE = "INCOMPLETE"

_DISALLOWED_GROUPING_KEYS = {
    "bubble_instance",
    "bubble_interior",
    "cleaning_eligibility",
    "contact_region",
    "layout_slot",
    "page_truncation",
    "panel_boundary",
    "physical_boundary",
    "physical_container",
    "safe_edit",
    "separator",
    "visible_bubble_boundary",
}


@dataclass(frozen=True)
class GroupingProducerIdentity:
    producer_name: str
    producer_version: str
    implementation_hash: str


@dataclass(frozen=True)
class GroupingInputFragment:
    fragment_id: str
    text_block_id: str
    reading_order: int
    bbox_json: str
    polygon_json: str
    geometry_hash: str
    coordinate_space_json: str
    ocr_result_id: str
    ocr_version_number: int
    ocr_text: str
    ocr_text_hash: str
    ocr_geometry_hash: str
    ocr_input_hash: str


@dataclass(frozen=True)
class GroupingProducerInput:
    project_id: str
    page_id: str
    source_artifact_id: str
    source_bytes: bytes
    source_sha256: str
    coordinate_space_json: str
    detection_dependency_id: str
    detection_dependency_hash: str
    profile_snapshot_id: str
    profile_settings_json: str
    profile_settings_hash: str
    producer: GroupingProducerIdentity
    operation_semantics_version: str
    fragments: tuple[GroupingInputFragment, ...]


@dataclass(frozen=True)
class GroupingCandidateFragmentDraft:
    fragment_id: str
    membership_provenance_json: str
    supporting_geometry_references_json: str = "{}"


@dataclass(frozen=True)
class GroupingTextGroupDraft:
    group_id: str
    ordered_fragment_ids: tuple[str, ...]
    group_order: int
    ordering_metadata_json: str
    membership_provenance_json: str
    supporting_geometry_references_json: str = "{}"
    unresolved_relation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GroupingUnresolvedRelationDraft:
    relation_id: str
    affected_fragment_ids: tuple[str, ...]
    affected_group_ids: tuple[str, ...]
    reason_code: str
    supporting_evidence_json: str


@dataclass(frozen=True)
class GroupingCandidateDraft:
    candidate_disposition: str
    fragments: tuple[GroupingCandidateFragmentDraft, ...]
    text_groups: tuple[GroupingTextGroupDraft, ...]
    unresolved_relations: tuple[GroupingUnresolvedRelationDraft, ...] = ()


@dataclass(frozen=True)
class GroupingProducerResult:
    outcome: str
    candidate: GroupingCandidateDraft | None = None
    reason_codes: tuple[str, ...] = ()
    error_code: str | None = None


class GroupingProducer(Protocol):
    identity: GroupingProducerIdentity

    def produce(self, input_data: GroupingProducerInput) -> GroupingProducerResult:
        ...


@dataclass(frozen=True)
class CanonicalGroupingManifest:
    snapshot_id: str
    dependency_fingerprint: str
    canonical_manifest_sha256: str
    canonical_bytes: bytes
    schema_version: str
    candidate_disposition: str
    fragment_ids: tuple[str, ...]
    text_block_ids: tuple[str, ...]
    ocr_result_ids: tuple[str, ...]


@dataclass(frozen=True)
class GroupingFingerprintOcrDependency:
    text_block_id: str
    ocr_result_id: str
    version_number: int
    text_hash: str
    geometry_hash: str
    input_hash: str


@dataclass(frozen=True)
class GroupingDependencyFingerprintInput:
    source_artifact_id: str
    source_sha256: str
    coordinate_space_json: str
    detection_dependency_id: str
    detection_dependency_hash: str
    profile_snapshot_id: str
    profile_settings_hash: str
    producer: GroupingProducerIdentity
    operation_semantics_version: str
    ocr_dependencies: tuple[GroupingFingerprintOcrDependency, ...]


def canonicalize_grouping_manifest(
    input_data: GroupingProducerInput,
    candidate: GroupingCandidateDraft,
) -> CanonicalGroupingManifest:
    canonical_inputs = _canonical_input_fragments(input_data)
    input_by_fragment = {
        fragment["fragment_id"]: fragment for fragment in canonical_inputs
    }
    canonical_fragments = _canonical_candidate_fragments(
        candidate.fragments,
        input_by_fragment=input_by_fragment,
    )
    canonical_groups = _canonical_groups(
        candidate.text_groups,
        fragment_ids=set(input_by_fragment),
    )
    canonical_relations = _canonical_relations(
        candidate.unresolved_relations,
        fragment_ids=set(input_by_fragment),
        group_ids={group["group_id"] for group in canonical_groups},
    )
    _validate_candidate_structure(
        candidate.candidate_disposition,
        canonical_fragments=canonical_fragments,
        canonical_groups=canonical_groups,
        canonical_relations=canonical_relations,
    )

    coordinate_space = _parse_json_object(
        "coordinate_space_json", input_data.coordinate_space_json
    )
    manifest = {
        "candidate_disposition": candidate.candidate_disposition,
        "coordinate_space": coordinate_space,
        "detection_dependency": {
            "dependency_hash": input_data.detection_dependency_hash,
            "dependency_id": input_data.detection_dependency_id,
        },
        "fragments": canonical_fragments,
        "ocr_dependencies": [
            {
                "geometry_hash": fragment["ocr"]["geometry_hash"],
                "input_hash": fragment["ocr"]["input_hash"],
                "ocr_result_id": fragment["ocr"]["ocr_result_id"],
                "text_block_id": fragment["text_block_id"],
                "text_hash": fragment["ocr"]["text_hash"],
                "version_number": fragment["ocr"]["version_number"],
            }
            for fragment in canonical_fragments
        ],
        "operation_semantics_version": input_data.operation_semantics_version,
        "page_id": input_data.page_id,
        "producer": {
            "implementation_hash": input_data.producer.implementation_hash,
            "name": input_data.producer.producer_name,
            "version": input_data.producer.producer_version,
        },
        "profile_snapshot": {
            "profile_snapshot_id": input_data.profile_snapshot_id,
            "settings_hash": input_data.profile_settings_hash,
        },
        "project_id": input_data.project_id,
        "schema_version": GROUPING_MANIFEST_SCHEMA_VERSION,
        "source_artifact_id": input_data.source_artifact_id,
        "source_sha256": input_data.source_sha256,
        "text_groups": canonical_groups,
        "unresolved_relations": canonical_relations,
    }
    _validate_semantic_input(input_data, coordinate_space)
    _validate_json_value(manifest)
    canonical_bytes = _canonical_json_bytes(manifest)
    manifest_hash = sha256(canonical_bytes).hexdigest()
    dependency_fingerprint = grouping_dependency_fingerprint(
        input_data=input_data,
        canonical_manifest_sha256=manifest_hash,
    )
    return CanonicalGroupingManifest(
        snapshot_id=f"{GROUPING_SNAPSHOT_ID_PREFIX}{dependency_fingerprint}",
        dependency_fingerprint=dependency_fingerprint,
        canonical_manifest_sha256=manifest_hash,
        canonical_bytes=canonical_bytes,
        schema_version=GROUPING_MANIFEST_SCHEMA_VERSION,
        candidate_disposition=candidate.candidate_disposition,
        fragment_ids=tuple(fragment["fragment_id"] for fragment in canonical_fragments),
        text_block_ids=tuple(fragment["text_block_id"] for fragment in canonical_fragments),
        ocr_result_ids=tuple(
            fragment["ocr"]["ocr_result_id"] for fragment in canonical_fragments
        ),
    )


def grouping_dependency_fingerprint(
    *,
    input_data: GroupingProducerInput,
    canonical_manifest_sha256: str,
) -> str:
    return grouping_dependency_fingerprint_from_bindings(
        input_data=GroupingDependencyFingerprintInput(
            source_artifact_id=input_data.source_artifact_id,
            source_sha256=input_data.source_sha256,
            coordinate_space_json=input_data.coordinate_space_json,
            detection_dependency_id=input_data.detection_dependency_id,
            detection_dependency_hash=input_data.detection_dependency_hash,
            profile_snapshot_id=input_data.profile_snapshot_id,
            profile_settings_hash=input_data.profile_settings_hash,
            producer=input_data.producer,
            operation_semantics_version=input_data.operation_semantics_version,
            ocr_dependencies=tuple(
                GroupingFingerprintOcrDependency(
                    text_block_id=fragment.text_block_id,
                    ocr_result_id=fragment.ocr_result_id,
                    version_number=fragment.ocr_version_number,
                    text_hash=fragment.ocr_text_hash,
                    geometry_hash=fragment.ocr_geometry_hash,
                    input_hash=fragment.ocr_input_hash,
                )
                for fragment in input_data.fragments
            ),
        ),
        canonical_manifest_sha256=canonical_manifest_sha256,
    )


def grouping_dependency_fingerprint_from_bindings(
    *,
    input_data: GroupingDependencyFingerprintInput,
    canonical_manifest_sha256: str,
) -> str:
    _require_sha256("canonical_manifest_sha256", canonical_manifest_sha256)
    for name, value in (
        ("source_artifact_id", input_data.source_artifact_id),
        ("detection_dependency_id", input_data.detection_dependency_id),
        ("profile_snapshot_id", input_data.profile_snapshot_id),
        ("producer_name", input_data.producer.producer_name),
        ("producer_version", input_data.producer.producer_version),
        ("operation_semantics_version", input_data.operation_semantics_version),
    ):
        _require_nonempty(name, value)
    for name, value in (
        ("source_sha256", input_data.source_sha256),
        ("detection_dependency_hash", input_data.detection_dependency_hash),
        ("profile_settings_hash", input_data.profile_settings_hash),
        ("producer_implementation_hash", input_data.producer.implementation_hash),
    ):
        _require_sha256(name, value)
    if input_data.detection_dependency_id != (
        f"detection-set-v1:{input_data.detection_dependency_hash}"
    ):
        raise ValueError("Grouping Detection dependency identity is inconsistent.")
    _reject_duplicate_ids(
        "Grouping fingerprint TextBlock",
        (item.text_block_id for item in input_data.ocr_dependencies),
    )
    _reject_duplicate_ids(
        "Grouping fingerprint OCR result",
        (item.ocr_result_id for item in input_data.ocr_dependencies),
    )
    for item in input_data.ocr_dependencies:
        if item.version_number < 1:
            raise ValueError("Grouping OCR dependency version is invalid.")
        for name, value in (
            ("ocr_text_hash", item.text_hash),
            ("ocr_geometry_hash", item.geometry_hash),
            ("ocr_input_hash", item.input_hash),
        ):
            _require_sha256(name, value)
    fingerprint_payload = {
        "canonical_manifest_sha256": canonical_manifest_sha256,
        "coordinate_space": _parse_json_object(
            "coordinate_space_json", input_data.coordinate_space_json
        ),
        "detection_dependency_hash": input_data.detection_dependency_hash,
        "detection_dependency_id": input_data.detection_dependency_id,
        "ocr_dependencies": [
            {
                "geometry_hash": fragment.geometry_hash,
                "input_hash": fragment.input_hash,
                "ocr_result_id": fragment.ocr_result_id,
                "text_block_id": fragment.text_block_id,
                "text_hash": fragment.text_hash,
                "version_number": fragment.version_number,
            }
            for fragment in sorted(
                input_data.ocr_dependencies,
                key=lambda item: item.text_block_id.encode("utf-8"),
            )
        ],
        "operation_semantics_version": input_data.operation_semantics_version,
        "producer": {
            "implementation_hash": input_data.producer.implementation_hash,
            "name": input_data.producer.producer_name,
            "version": input_data.producer.producer_version,
        },
        "profile_snapshot_id": input_data.profile_snapshot_id,
        "profile_settings_hash": input_data.profile_settings_hash,
        "source_artifact_id": input_data.source_artifact_id,
        "source_sha256": input_data.source_sha256,
    }
    return sha256(_canonical_json_bytes(fingerprint_payload)).hexdigest()


def _canonical_input_fragments(
    input_data: GroupingProducerInput,
) -> list[dict[str, Any]]:
    if not input_data.fragments:
        raise ValueError("Grouping producer input cannot be empty.")
    sorted_fragments = sorted(
        input_data.fragments,
        key=lambda fragment: fragment.fragment_id.encode("utf-8"),
    )
    _reject_duplicate_ids(
        "Grouping input fragment", (fragment.fragment_id for fragment in sorted_fragments)
    )
    _reject_duplicate_ids(
        "Grouping input text block",
        (fragment.text_block_id for fragment in sorted_fragments),
    )
    _reject_duplicate_ids(
        "Grouping input OCR result",
        (fragment.ocr_result_id for fragment in sorted_fragments),
    )
    result = []
    for fragment in sorted_fragments:
        _require_nonempty("fragment_id", fragment.fragment_id)
        _require_nonempty("text_block_id", fragment.text_block_id)
        _require_nonempty("ocr_result_id", fragment.ocr_result_id)
        if fragment.reading_order < 0 or fragment.ocr_version_number < 1:
            raise ValueError("Grouping fragment ordering/version is invalid.")
        for name, value in (
            ("geometry_hash", fragment.geometry_hash),
            ("ocr_text_hash", fragment.ocr_text_hash),
            ("ocr_geometry_hash", fragment.ocr_geometry_hash),
            ("ocr_input_hash", fragment.ocr_input_hash),
        ):
            _require_sha256(name, value)
        if sha256(fragment.ocr_text.encode("utf-8")).hexdigest() != fragment.ocr_text_hash:
            raise ValueError("Grouping OCR text does not match its text hash.")
        coordinate_space = _parse_json_object(
            "fragment.coordinate_space_json", fragment.coordinate_space_json
        )
        if coordinate_space != _parse_json_object(
            "coordinate_space_json", input_data.coordinate_space_json
        ):
            raise ValueError("Grouping fragment coordinate-space binding is invalid.")
        if fragment.ocr_geometry_hash != fragment.geometry_hash:
            raise ValueError("Grouping OCR geometry does not match Detection geometry.")
        result.append(
            {
                "bbox": _parse_json_object("bbox_json", fragment.bbox_json),
                "coordinate_space": coordinate_space,
                "fragment_id": fragment.fragment_id,
                "geometry_hash": fragment.geometry_hash,
                "ocr": {
                    "geometry_hash": fragment.ocr_geometry_hash,
                    "input_hash": fragment.ocr_input_hash,
                    "ocr_result_id": fragment.ocr_result_id,
                    "text_hash": fragment.ocr_text_hash,
                    "version_number": fragment.ocr_version_number,
                },
                "polygon": _parse_json_value("polygon_json", fragment.polygon_json),
                "reading_order": fragment.reading_order,
                "text_block_id": fragment.text_block_id,
            }
        )
    return result


def _canonical_candidate_fragments(
    fragments: tuple[GroupingCandidateFragmentDraft, ...],
    *,
    input_by_fragment: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    sorted_fragments = sorted(
        fragments, key=lambda fragment: fragment.fragment_id.encode("utf-8")
    )
    _reject_duplicate_ids(
        "Grouping candidate fragment",
        (fragment.fragment_id for fragment in sorted_fragments),
    )
    if {fragment.fragment_id for fragment in sorted_fragments} != set(input_by_fragment):
        raise ValueError("Grouping candidate fragments must match the exact input set.")
    result = []
    for fragment in sorted_fragments:
        provenance = _parse_json_object(
            "fragment.membership_provenance_json",
            fragment.membership_provenance_json,
        )
        if not provenance:
            raise ValueError("Grouping fragment membership provenance is required.")
        supporting = _parse_json_value(
            "fragment.supporting_geometry_references_json",
            fragment.supporting_geometry_references_json,
        )
        _reject_physical_boundary_fields(provenance)
        _reject_physical_boundary_fields(supporting)
        result.append(
            {
                **input_by_fragment[fragment.fragment_id],
                "membership_provenance": provenance,
                "supporting_geometry_references": supporting,
            }
        )
    return result


def _canonical_groups(
    groups: tuple[GroupingTextGroupDraft, ...],
    *,
    fragment_ids: set[str],
) -> list[dict[str, Any]]:
    sorted_groups = sorted(groups, key=lambda group: group.group_id.encode("utf-8"))
    _reject_duplicate_ids("Grouping text group", (group.group_id for group in sorted_groups))
    group_orders: set[int] = set()
    result = []
    for group in sorted_groups:
        _require_nonempty("group_id", group.group_id)
        if group.group_order < 0 or group.group_order in group_orders:
            raise ValueError("Grouping group ordering metadata is invalid or duplicate.")
        group_orders.add(group.group_order)
        if not group.ordered_fragment_ids:
            raise ValueError("Grouping text groups cannot be empty.")
        if len(set(group.ordered_fragment_ids)) != len(group.ordered_fragment_ids):
            raise ValueError("Grouping group contains duplicate fragment membership.")
        if not set(group.ordered_fragment_ids).issubset(fragment_ids):
            raise ValueError("Grouping group contains a dangling fragment reference.")
        ordering = _parse_json_object(
            "group.ordering_metadata_json", group.ordering_metadata_json
        )
        provenance = _parse_json_object(
            "group.membership_provenance_json", group.membership_provenance_json
        )
        if not ordering or not provenance:
            raise ValueError("Grouping ordering and membership provenance are required.")
        supporting = _parse_json_value(
            "group.supporting_geometry_references_json",
            group.supporting_geometry_references_json,
        )
        for value in (ordering, provenance, supporting):
            _reject_physical_boundary_fields(value)
        result.append(
            {
                "group_id": group.group_id,
                "group_order": group.group_order,
                "membership_provenance": provenance,
                "ordered_fragment_ids": list(group.ordered_fragment_ids),
                "ordering_metadata": ordering,
                "supporting_geometry_references": supporting,
                "unresolved_relation_ids": sorted(
                    group.unresolved_relation_ids, key=lambda value: value.encode("utf-8")
                ),
            }
        )
    return result


def _canonical_relations(
    relations: tuple[GroupingUnresolvedRelationDraft, ...],
    *,
    fragment_ids: set[str],
    group_ids: set[str],
) -> list[dict[str, Any]]:
    sorted_relations = sorted(
        relations, key=lambda relation: relation.relation_id.encode("utf-8")
    )
    _reject_duplicate_ids(
        "Grouping unresolved relation",
        (relation.relation_id for relation in sorted_relations),
    )
    result = []
    for relation in sorted_relations:
        _require_nonempty("relation_id", relation.relation_id)
        _require_nonempty("reason_code", relation.reason_code)
        affected_fragments = tuple(
            sorted(set(relation.affected_fragment_ids), key=lambda value: value.encode("utf-8"))
        )
        affected_groups = tuple(
            sorted(set(relation.affected_group_ids), key=lambda value: value.encode("utf-8"))
        )
        if len(affected_fragments) != len(relation.affected_fragment_ids) or len(
            affected_groups
        ) != len(relation.affected_group_ids):
            raise ValueError("Grouping unresolved relation contains duplicate references.")
        if not affected_fragments and not affected_groups:
            raise ValueError("Grouping unresolved relation must identify affected facts.")
        if not set(affected_fragments).issubset(fragment_ids) or not set(
            affected_groups
        ).issubset(group_ids):
            raise ValueError("Grouping unresolved relation contains a dangling reference.")
        supporting = _parse_json_object(
            "relation.supporting_evidence_json", relation.supporting_evidence_json
        )
        if not supporting:
            raise ValueError("Grouping unresolved relation evidence is required.")
        _reject_physical_boundary_fields(supporting)
        result.append(
            {
                "affected_fragment_ids": list(affected_fragments),
                "affected_group_ids": list(affected_groups),
                "reason_code": relation.reason_code,
                "relation_id": relation.relation_id,
                "supporting_evidence": supporting,
            }
        )
    return result


def _validate_candidate_structure(
    disposition: str,
    *,
    canonical_fragments: list[dict[str, Any]],
    canonical_groups: list[dict[str, Any]],
    canonical_relations: list[dict[str, Any]],
) -> None:
    if disposition not in {
        GROUPING_DISPOSITION_PRODUCED,
        GROUPING_DISPOSITION_INCOMPLETE,
    }:
        raise ValueError("Grouping candidate disposition is invalid.")
    memberships: dict[str, str] = {}
    relation_ids = {relation["relation_id"] for relation in canonical_relations}
    for group in canonical_groups:
        if not set(group["unresolved_relation_ids"]).issubset(relation_ids):
            raise ValueError("Grouping group contains a dangling unresolved relation.")
        for fragment_id in group["ordered_fragment_ids"]:
            if fragment_id in memberships:
                raise ValueError("Grouping fragment has incompatible duplicate membership.")
            memberships[fragment_id] = group["group_id"]
    unassigned = {
        fragment["fragment_id"] for fragment in canonical_fragments
    } - set(memberships)
    explicitly_unresolved = {
        fragment_id
        for relation in canonical_relations
        for fragment_id in relation["affected_fragment_ids"]
    }
    if not unassigned.issubset(explicitly_unresolved):
        raise ValueError("Grouping candidate hides unassigned fragments.")
    has_incomplete_facts = bool(unassigned or canonical_relations)
    if disposition == GROUPING_DISPOSITION_PRODUCED and has_incomplete_facts:
        raise ValueError("PRODUCED Grouping candidate cannot contain unresolved facts.")
    if disposition == GROUPING_DISPOSITION_INCOMPLETE and not has_incomplete_facts:
        raise ValueError("INCOMPLETE Grouping candidate must identify unresolved facts.")


def _validate_semantic_input(
    input_data: GroupingProducerInput,
    coordinate_space: dict[str, Any],
) -> None:
    for name, value in (
        ("project_id", input_data.project_id),
        ("page_id", input_data.page_id),
        ("source_artifact_id", input_data.source_artifact_id),
        ("detection_dependency_id", input_data.detection_dependency_id),
        ("profile_snapshot_id", input_data.profile_snapshot_id),
        ("producer_name", input_data.producer.producer_name),
        ("producer_version", input_data.producer.producer_version),
        ("operation_semantics_version", input_data.operation_semantics_version),
    ):
        _require_nonempty(name, value)
    for name, value in (
        ("source_sha256", input_data.source_sha256),
        ("detection_dependency_hash", input_data.detection_dependency_hash),
        ("profile_settings_hash", input_data.profile_settings_hash),
        ("producer_implementation_hash", input_data.producer.implementation_hash),
    ):
        _require_sha256(name, value)
    if sha256(input_data.source_bytes).hexdigest() != input_data.source_sha256:
        raise ValueError("Grouping source bytes do not match the source hash.")
    try:
        profile_settings = json.loads(input_data.profile_settings_json)
    except json.JSONDecodeError as exc:
        raise ValueError("Grouping profile settings are malformed.") from exc
    _validate_json_value(profile_settings)
    if (
        sha256(input_data.profile_settings_json.encode("utf-8")).hexdigest()
        != input_data.profile_settings_hash
    ):
        raise ValueError("Grouping profile settings hash is inconsistent.")
    if input_data.detection_dependency_id != (
        f"detection-set-v1:{input_data.detection_dependency_hash}"
    ):
        raise ValueError("Grouping Detection dependency identity is inconsistent.")
    if not coordinate_space:
        raise ValueError("Grouping coordinate-space binding is required.")


def _reject_physical_boundary_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.lower().replace("-", "_")
            if any(token in normalized for token in _DISALLOWED_GROUPING_KEYS):
                raise ValueError(
                    f"Grouping manifest contains disallowed Physical Boundary field: {key}"
                )
            _reject_physical_boundary_fields(item)
    elif isinstance(value, list):
        for item in value:
            _reject_physical_boundary_fields(item)


def _reject_duplicate_ids(name: str, values) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"Duplicate {name} identity: {value}")
        seen.add(value)


def _canonical_json_bytes(value: Any) -> bytes:
    _validate_json_value(value)
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


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
            raise ValueError("Canonical Grouping evidence only accepts finite numbers.")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Canonical Grouping evidence keys must be strings.")
            _validate_json_value(item)
        return
    raise ValueError(f"Unsupported canonical Grouping value: {type(value)!r}")


def _require_nonempty(name: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string.")


def _require_sha256(name: str, value: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest.")
