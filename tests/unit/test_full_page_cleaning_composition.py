from __future__ import annotations

from hashlib import sha256
from io import BytesIO

from PIL import Image

from manga_read_flow.cleaning.full_page import (
    CompositionMember,
    PageCleaningValidationInput,
    PageValidationMember,
    compose_full_page_cleaning,
    validate_full_page_cleaning,
)


def _png(mode: str, pixels, size=(4, 2)) -> bytes:
    image = Image.new(mode, size)
    image.putdata(pixels)
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _rgb(values) -> bytes:
    return _png("RGB", [(value, value, value) for value in values])


def _mask(on_indexes, size=(4, 2)) -> bytes:
    count = size[0] * size[1]
    return _png("L", [255 if index in on_indexes else 0 for index in range(count)], size)


def test_composition_replays_canonical_members_from_original_without_mutation():
    original = _rgb([0] * 8)
    original_hash = sha256(original).hexdigest()
    member_a = CompositionMember(
        instance_cleaning_result_id="result-a",
        composition_key="02/a",
        candidate_png=_rgb([0, 0, 0, 0, 0, 0, 70, 0]),
        actual_changed_mask_png=_mask({6}),
    )
    member_b = CompositionMember(
        instance_cleaning_result_id="result-b",
        composition_key="01/b",
        candidate_png=_rgb([0, 50, 0, 0, 0, 0, 0, 0]),
        actual_changed_mask_png=_mask({1}),
    )

    first = compose_full_page_cleaning(original, (member_a, member_b))
    replay = compose_full_page_cleaning(original, (member_b, member_a))

    assert first.combined_png == replay.combined_png
    assert first.combined_delta_mask_png == replay.combined_delta_mask_png
    assert first.member_set_fingerprint == replay.member_set_fingerprint
    assert first.ordered_result_ids == ("result-b", "result-a")
    assert sha256(original).hexdigest() == original_hash
    with Image.open(BytesIO(first.combined_png)) as image:
        assert [pixel[0] for pixel in image.getdata()] == [0, 50, 0, 0, 0, 0, 70, 0]


def test_page_validator_passes_complete_non_overlapping_fresh_composition():
    original = _rgb([0] * 8)
    members = (
        CompositionMember("result-a", "01/a", _rgb([40, 0, 0, 0, 0, 0, 0, 0]), _mask({0})),
        CompositionMember("result-b", "02/b", _rgb([0, 0, 0, 0, 0, 0, 0, 60]), _mask({7})),
    )
    composed = compose_full_page_cleaning(original, members)

    result = validate_full_page_cleaning(
        PageCleaningValidationInput(
            original_png=original,
            expected_source_hash=sha256(original).hexdigest(),
            combined_png=composed.combined_png,
            expected_combined_hash=sha256(composed.combined_png).hexdigest(),
            combined_delta_mask_png=composed.combined_delta_mask_png,
            inventory_item_ids=("inventory-a", "inventory-b"),
            members=(
                PageValidationMember(
                    "result-a", ("inventory-a",), _mask({0}), _mask({0}), _mask({0}),
                    _mask(set()), _mask(set()), 0, 0, True,
                ),
                PageValidationMember(
                    "result-b", ("inventory-b",), _mask({7}), _mask({7}), _mask({7}),
                    _mask(set()), _mask(set()), 0, 0, True,
                ),
            ),
        )
    )

    assert result.status == "pass"
    assert result.missing_attribution_count == 0
    assert result.duplicate_attribution_count == 0
    assert result.pairwise_overlap_pixel_count == 0
    assert result.wrong_instance_write_pixel_count == 0
    assert result.combined_delta_matches_member_union is True


def test_page_validator_rejects_attribution_cross_write_and_pixel_safety_failures():
    original = _rgb([0] * 8)
    combined = _rgb([90, 90, 90, 0, 0, 0, 0, 0])

    result = validate_full_page_cleaning(
        PageCleaningValidationInput(
            original_png=original,
            expected_source_hash=sha256(original).hexdigest(),
            combined_png=combined,
            expected_combined_hash="wrong-combined-hash",
            combined_delta_mask_png=_mask({0, 1}),
            inventory_item_ids=("inventory-a", "inventory-b", "inventory-missing"),
            members=(
                PageValidationMember(
                    "result-a", ("inventory-a", "inventory-b"), _mask({0, 1}),
                    _mask({0}), _mask({0}), _mask({1}), _mask(set()), 2, 3, True,
                ),
                PageValidationMember(
                    "result-b", ("inventory-b",), _mask({1, 2}),
                    _mask({2}), _mask({2}), _mask(set()), _mask({1}), 0, 0, False,
                ),
            ),
        )
    )

    assert result.status == "fail"
    assert result.missing_attribution_count == 1
    assert result.duplicate_attribution_count == 1
    assert result.pairwise_overlap_pixel_count == 1
    assert result.wrong_instance_write_pixel_count == 2
    assert result.outside_safe_pixel_count == 2
    assert result.protected_pixel_count == 1
    assert result.uncertainty_pixel_count == 1
    assert result.boundary_damage_pixel_count == 2
    assert result.residue_pixel_count == 3
    assert result.combined_integrity_valid is False
    assert result.dependencies_fresh is False
    assert result.combined_delta_matches_member_union is False
