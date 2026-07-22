from __future__ import annotations

from dataclasses import replace

import pytest

from manga_read_flow.domain.detection_evidence import (
    AcceptedDetectionEvidenceMember,
    AcceptedDetectionEvidenceSemanticInput,
    StableDetectionProviderIdentity,
    canonicalize_detection_evidence,
)


HASH_A = "a" * 64
HASH_B = "b" * 64


def _member(text_block_id: str, *, reading_order: int) -> AcceptedDetectionEvidenceMember:
    return AcceptedDetectionEvidenceMember(
        text_block_id=text_block_id,
        project_id="project",
        page_id="page",
        reading_order=reading_order,
        bbox_json='{"x":1,"y":2,"width":3,"height":4}',
        polygon_json="[[1,2],[4,2],[4,6],[1,6]]",
        geometry_hash=HASH_A,
        coordinate_space_json='{"unit":"pixel","origin":"top_left"}',
        detection_provider="provider",
        detection_confidence=0.9,
    )


def _input() -> AcceptedDetectionEvidenceSemanticInput:
    return AcceptedDetectionEvidenceSemanticInput(
        project_id="project",
        page_id="page",
        source_artifact_id="source",
        source_sha256=HASH_A,
        coordinate_space_json='{"origin":"top_left","unit":"pixel"}',
        detection_config_hash=HASH_B,
        provider=StableDetectionProviderIdentity(
            provider_name="provider",
            provider_kind="local",
            model_id="model",
            tool_name="detector",
            tool_version="1.0",
        ),
        members=(
            _member("block-b", reading_order=2),
            _member("block-a", reading_order=1),
        ),
    )


def test_canonical_detection_evidence_is_stable_across_input_and_mapping_order():
    original = canonicalize_detection_evidence(_input())
    reordered_members = replace(_input(), members=tuple(reversed(_input().members)))
    reordered_mappings = replace(
        reordered_members,
        coordinate_space_json='{"unit":"pixel","origin":"top_left"}',
        members=tuple(
            replace(
                member,
                bbox_json='{"height":4,"width":3,"y":2,"x":1}',
            )
            for member in reordered_members.members
        ),
    )
    repeated = canonicalize_detection_evidence(reordered_mappings)

    assert repeated.canonical_bytes == original.canonical_bytes
    assert repeated.canonical_manifest_sha256 == original.canonical_manifest_sha256
    assert repeated.detection_dependency_id == original.detection_dependency_id
    assert original.member_ids == ("block-a", "block-b")


@pytest.mark.parametrize(
    "changed",
    [
        replace(_input(), source_sha256="c" * 64),
        replace(
            _input(),
            coordinate_space_json='{"origin":"center","unit":"pixel"}',
            members=tuple(
                replace(
                    member,
                    coordinate_space_json='{"origin":"center","unit":"pixel"}',
                )
                for member in _input().members
            ),
        ),
        replace(_input(), detection_config_hash="c" * 64),
        replace(
            _input(),
            provider=replace(_input().provider, tool_version="2.0"),
        ),
        replace(_input(), schema_version="accepted-detection-evidence-set.v2"),
        replace(
            _input(),
            members=(replace(_input().members[0], reading_order=3), _input().members[1]),
        ),
        replace(
            _input(),
            members=(
                replace(_input().members[0], geometry_hash="c" * 64),
                _input().members[1],
            ),
        ),
    ],
)
def test_semantic_changes_change_detection_dependency_identity(changed):
    assert (
        canonicalize_detection_evidence(changed).detection_dependency_id
        != canonicalize_detection_evidence(_input()).detection_dependency_id
    )


def test_execution_provenance_is_not_part_of_semantic_input_or_hash():
    first = canonicalize_detection_evidence(_input())
    second = canonicalize_detection_evidence(_input())

    assert first.detection_dependency_id == second.detection_dependency_id
    assert b"attempt" not in first.canonical_bytes
    assert b"decision" not in first.canonical_bytes
    assert b"accepted_at" not in first.canonical_bytes
    assert b"path" not in first.canonical_bytes
    assert b"mtime" not in first.canonical_bytes


def test_duplicate_member_identity_is_rejected():
    duplicate = replace(
        _input(),
        members=(_member("block-a", reading_order=1), _member("block-a", reading_order=2)),
    )

    with pytest.raises(ValueError, match="Duplicate"):
        canonicalize_detection_evidence(duplicate)


@pytest.mark.parametrize(
    "member",
    [
        replace(_member("block-a", reading_order=1), detection_confidence=float("nan")),
        replace(_member("block-a", reading_order=1), bbox_json='{"x":NaN}'),
    ],
)
def test_non_finite_numbers_are_rejected(member):
    with pytest.raises(ValueError, match="finite"):
        canonicalize_detection_evidence(replace(_input(), members=(member,)))
