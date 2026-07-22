from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

from manga_read_flow.domain.grouping import (
    GROUPING_DISPOSITION_INCOMPLETE,
    GROUPING_DISPOSITION_PRODUCED,
    GroupingCandidateDraft,
    GroupingCandidateFragmentDraft,
    GroupingInputFragment,
    GroupingProducerIdentity,
    GroupingProducerInput,
    GroupingTextGroupDraft,
    GroupingUnresolvedRelationDraft,
    canonicalize_grouping_manifest,
)


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
SOURCE_BYTES = b"source-image-bytes"
SOURCE_HASH = sha256(SOURCE_BYTES).hexdigest()
PROFILE_JSON = '{"mode":"test"}'
PROFILE_HASH = sha256(PROFILE_JSON.encode("utf-8")).hexdigest()


def _input() -> GroupingProducerInput:
    return GroupingProducerInput(
        project_id="project",
        page_id="page",
        source_artifact_id="source",
        source_bytes=SOURCE_BYTES,
        source_sha256=SOURCE_HASH,
        coordinate_space_json='{"origin":"top_left","unit":"pixel"}',
        detection_dependency_id=f"detection-set-v1:{HASH_D}",
        detection_dependency_hash=HASH_D,
        profile_snapshot_id="profile",
        profile_settings_json=PROFILE_JSON,
        profile_settings_hash=PROFILE_HASH,
        producer=GroupingProducerIdentity("producer", "1", HASH_B),
        operation_semantics_version="grouping-op.v1",
        fragments=(
            _input_fragment("fragment-b", 2, HASH_B, "beta"),
            _input_fragment("fragment-a", 1, HASH_A, "alpha"),
        ),
    )


def _input_fragment(
    fragment_id: str,
    reading_order: int,
    geometry_hash: str,
    text: str,
) -> GroupingInputFragment:
    return GroupingInputFragment(
        fragment_id=fragment_id,
        text_block_id=fragment_id,
        reading_order=reading_order,
        bbox_json='{"x":1,"y":2,"width":3,"height":4}',
        polygon_json="[[1,2],[4,2],[4,6],[1,6]]",
        geometry_hash=geometry_hash,
        coordinate_space_json='{"unit":"pixel","origin":"top_left"}',
        ocr_result_id=f"ocr-{fragment_id}",
        ocr_version_number=1,
        ocr_text=text,
        ocr_text_hash=sha256(text.encode("utf-8")).hexdigest(),
        ocr_geometry_hash=geometry_hash,
        ocr_input_hash=HASH_C,
    )


def _candidate() -> GroupingCandidateDraft:
    return GroupingCandidateDraft(
        candidate_disposition=GROUPING_DISPOSITION_PRODUCED,
        fragments=tuple(
            GroupingCandidateFragmentDraft(
                fragment_id=fragment_id,
                membership_provenance_json='{"kind":"producer_membership"}',
            )
            for fragment_id in ("fragment-b", "fragment-a")
        ),
        text_groups=(
            GroupingTextGroupDraft(
                group_id="group-main",
                ordered_fragment_ids=("fragment-a", "fragment-b"),
                group_order=0,
                ordering_metadata_json='{"basis":"m1_reading_order"}',
                membership_provenance_json='{"kind":"producer_membership"}',
            ),
        ),
    )


def _two_group_candidate() -> GroupingCandidateDraft:
    return replace(
        _candidate(),
        text_groups=(
            GroupingTextGroupDraft(
                "group-b",
                ("fragment-b",),
                1,
                '{"basis":"m1_reading_order"}',
                '{"kind":"producer_membership"}',
            ),
            GroupingTextGroupDraft(
                "group-a",
                ("fragment-a",),
                0,
                '{"basis":"m1_reading_order"}',
                '{"kind":"producer_membership"}',
            ),
        ),
    )


def _incomplete_candidate() -> GroupingCandidateDraft:
    return replace(
        _candidate(),
        candidate_disposition=GROUPING_DISPOSITION_INCOMPLETE,
        text_groups=(
            replace(
                _candidate().text_groups[0],
                ordered_fragment_ids=("fragment-a",),
                unresolved_relation_ids=("relation-b", "relation-a"),
            ),
        ),
        unresolved_relations=(
            GroupingUnresolvedRelationDraft(
                "relation-b",
                ("fragment-b",),
                (),
                "membership_uncertain",
                '{"evidence":"proposal-b"}',
            ),
            GroupingUnresolvedRelationDraft(
                "relation-a",
                ("fragment-a",),
                ("group-main",),
                "relation_uncertain",
                '{"evidence":"proposal-a"}',
            ),
        ),
    )


def test_canonical_manifest_is_stable_across_fragment_and_mapping_order():
    first = canonicalize_grouping_manifest(_input(), _candidate())
    reordered_input = replace(_input(), fragments=tuple(reversed(_input().fragments)))
    reordered_candidate = replace(
        _candidate(),
        fragments=tuple(reversed(_candidate().fragments)),
        text_groups=(
            replace(
                _candidate().text_groups[0],
                ordering_metadata_json='{"basis":"m1_reading_order"}',
            ),
        ),
    )

    second = canonicalize_grouping_manifest(reordered_input, reordered_candidate)

    assert second.canonical_bytes == first.canonical_bytes
    assert second.canonical_manifest_sha256 == first.canonical_manifest_sha256
    assert second.dependency_fingerprint == first.dependency_fingerprint


def test_group_and_relation_collection_order_does_not_change_identity():
    groups = _two_group_candidate()
    first = canonicalize_grouping_manifest(_input(), groups)
    second = canonicalize_grouping_manifest(
        _input(), replace(groups, text_groups=tuple(reversed(groups.text_groups)))
    )
    incomplete = _incomplete_candidate()
    relation_first = canonicalize_grouping_manifest(_input(), incomplete)
    relation_second = canonicalize_grouping_manifest(
        _input(),
        replace(
            incomplete,
            unresolved_relations=tuple(reversed(incomplete.unresolved_relations)),
        ),
    )

    assert first.canonical_bytes == second.canonical_bytes
    assert relation_first.canonical_bytes == relation_second.canonical_bytes


@pytest.mark.parametrize(
    "candidate",
    [
        replace(
            _candidate(),
            text_groups=(
                replace(
                    _candidate().text_groups[0],
                    ordered_fragment_ids=("fragment-b", "fragment-a"),
                ),
            ),
        ),
        _two_group_candidate(),
        replace(
            _incomplete_candidate(),
            unresolved_relations=(
                replace(
                    _incomplete_candidate().unresolved_relations[0],
                    reason_code="different_reason",
                ),
                _incomplete_candidate().unresolved_relations[1],
            ),
        ),
    ],
)
def test_grouping_semantic_changes_change_manifest_identity(candidate):
    assert (
        canonicalize_grouping_manifest(_input(), candidate).canonical_manifest_sha256
        != canonicalize_grouping_manifest(_input(), _candidate()).canonical_manifest_sha256
    )


@pytest.mark.parametrize(
    "changed_input",
    [
        replace(
            _input(),
            fragments=(
                replace(
                    _input().fragments[0],
                    ocr_result_id="ocr-revision-2",
                    ocr_text="changed",
                    ocr_text_hash=sha256(b"changed").hexdigest(),
                ),
                _input().fragments[1],
            ),
        ),
        replace(
            _input(),
            detection_dependency_id=f"detection-set-v1:{HASH_C}",
            detection_dependency_hash=HASH_C,
        ),
        replace(_input(), profile_snapshot_id="profile-v2"),
        replace(
            _input(),
            producer=GroupingProducerIdentity("producer", "2", HASH_B),
        ),
        replace(_input(), operation_semantics_version="grouping-op.v2"),
    ],
)
def test_dependency_changes_change_fingerprint(changed_input):
    assert (
        canonicalize_grouping_manifest(changed_input, _candidate()).dependency_fingerprint
        != canonicalize_grouping_manifest(_input(), _candidate()).dependency_fingerprint
    )


@pytest.mark.parametrize(
    "candidate,match",
    [
        (
            replace(
                _candidate(),
                fragments=(_candidate().fragments[0], _candidate().fragments[0]),
            ),
            "Duplicate Grouping candidate fragment",
        ),
        (
            replace(
                _candidate(),
                text_groups=(
                    _candidate().text_groups[0],
                    _candidate().text_groups[0],
                ),
            ),
            "Duplicate Grouping text group",
        ),
        (
            replace(
                _incomplete_candidate(),
                unresolved_relations=(
                    _incomplete_candidate().unresolved_relations[0],
                    _incomplete_candidate().unresolved_relations[0],
                ),
            ),
            "Duplicate Grouping unresolved relation",
        ),
        (
            replace(
                _candidate(),
                text_groups=(
                    replace(
                        _candidate().text_groups[0],
                        ordered_fragment_ids=("fragment-a", "dangling"),
                    ),
                ),
            ),
            "dangling fragment",
        ),
        (
            replace(
                _two_group_candidate(),
                text_groups=(
                    _two_group_candidate().text_groups[0],
                    replace(
                        _two_group_candidate().text_groups[1],
                        ordered_fragment_ids=("fragment-a", "fragment-b"),
                    ),
                ),
            ),
            "incompatible duplicate membership",
        ),
    ],
)
def test_duplicate_dangling_and_incompatible_membership_are_rejected(
    candidate, match
):
    with pytest.raises(ValueError, match=match):
        canonicalize_grouping_manifest(_input(), candidate)


def test_non_finite_numbers_and_physical_boundary_fields_are_rejected():
    non_finite = replace(
        _candidate(),
        text_groups=(
            replace(
                _candidate().text_groups[0],
                ordering_metadata_json='{"score":NaN}',
            ),
        ),
    )
    physical = replace(
        _candidate(),
        text_groups=(
            replace(
                _candidate().text_groups[0],
                supporting_geometry_references_json='{"physical_boundary":"fake"}',
            ),
        ),
    )

    with pytest.raises(ValueError, match="finite"):
        canonicalize_grouping_manifest(_input(), non_finite)
    with pytest.raises(ValueError, match="Physical Boundary"):
        canonicalize_grouping_manifest(_input(), physical)


def test_non_candidate_disposition_is_rejected():
    with pytest.raises(ValueError, match="disposition"):
        canonicalize_grouping_manifest(
            _input(),
            replace(_candidate(), candidate_disposition="ACCEPTED"),
        )
