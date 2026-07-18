from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json

from PIL import Image


@dataclass(frozen=True)
class CompositionMember:
    instance_cleaning_result_id: str
    composition_key: str
    candidate_png: bytes
    actual_changed_mask_png: bytes


@dataclass(frozen=True)
class FullPageCompositionResult:
    combined_png: bytes
    combined_delta_mask_png: bytes
    combined_hash: str
    combined_delta_hash: str
    member_set_fingerprint: str
    ordered_result_ids: tuple[str, ...]


@dataclass(frozen=True)
class PageValidationMember:
    instance_cleaning_result_id: str
    inventory_item_ids: tuple[str, ...]
    actual_changed_mask_png: bytes
    instance_ownership_mask_png: bytes
    safe_edit_mask_png: bytes
    protected_mask_png: bytes
    uncertainty_mask_png: bytes
    boundary_damage_pixel_count: int
    residue_pixel_count: int
    dependencies_fresh: bool


@dataclass(frozen=True)
class PageCleaningValidationInput:
    original_png: bytes
    expected_source_hash: str
    combined_png: bytes
    expected_combined_hash: str
    combined_delta_mask_png: bytes
    inventory_item_ids: tuple[str, ...]
    members: tuple[PageValidationMember, ...]
    existing_dispositions: tuple[tuple[str, str, bool], ...] = ()


@dataclass(frozen=True)
class PageCleaningValidationResult:
    status: str
    inventory_complete: bool
    dispositions_unique: bool
    missing_attribution_count: int
    duplicate_attribution_count: int
    pairwise_overlap_pixel_count: int
    wrong_instance_write_pixel_count: int
    outside_safe_pixel_count: int
    protected_pixel_count: int
    uncertainty_pixel_count: int
    boundary_damage_pixel_count: int
    residue_pixel_count: int
    combined_delta_matches_member_union: bool
    source_integrity_valid: bool
    combined_integrity_valid: bool
    dependencies_fresh: bool
    validator_summary: str


def compose_full_page_cleaning(
    original_png: bytes,
    members: tuple[CompositionMember, ...],
) -> FullPageCompositionResult:
    """Deterministically copy every member's actual write from the same original."""
    if not members:
        raise ValueError("Full-page composition requires at least one member.")
    ordered = tuple(sorted(members, key=lambda member: member.composition_key))
    if len({member.composition_key for member in ordered}) != len(ordered):
        raise ValueError("Composition keys must be unique.")
    if len({member.instance_cleaning_result_id for member in ordered}) != len(ordered):
        raise ValueError("Composition members must reference unique instance results.")

    original = _load_image(original_png)
    combined = original.copy()
    combined_pixels = list(combined.getdata())
    union = [False] * (original.width * original.height)
    fingerprint_members = []

    for member in ordered:
        candidate = _load_image(member.candidate_png)
        _require_same_image_contract(original, candidate)
        mask = _load_mask(member.actual_changed_mask_png, original.size)
        candidate_pixels = list(candidate.getdata())
        for index, selected in enumerate(mask):
            if selected:
                combined_pixels[index] = candidate_pixels[index]
                union[index] = True
        fingerprint_members.append(
            {
                "composition_key": member.composition_key,
                "instance_cleaning_result_id": member.instance_cleaning_result_id,
                "candidate_hash": sha256(member.candidate_png).hexdigest(),
                "actual_changed_hash": sha256(member.actual_changed_mask_png).hexdigest(),
            }
        )

    combined.putdata(combined_pixels)
    combined_png = _encode_png(combined)
    delta_png = _encode_mask(union, original.size)
    fingerprint = sha256(
        json.dumps(fingerprint_members, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return FullPageCompositionResult(
        combined_png=combined_png,
        combined_delta_mask_png=delta_png,
        combined_hash=sha256(combined_png).hexdigest(),
        combined_delta_hash=sha256(delta_png).hexdigest(),
        member_set_fingerprint=fingerprint,
        ordered_result_ids=tuple(
            member.instance_cleaning_result_id for member in ordered
        ),
    )


def validate_full_page_cleaning(
    validation_input: PageCleaningValidationInput,
) -> PageCleaningValidationResult:
    original = _load_image(validation_input.original_png)
    combined = _load_image(validation_input.combined_png)
    _require_same_image_contract(original, combined)
    provided_delta = _load_mask(
        validation_input.combined_delta_mask_png,
        original.size,
    )
    actual_combined_delta = [
        source != output
        for source, output in zip(original.getdata(), combined.getdata(), strict=True)
    ]

    target_counts = {item_id: 0 for item_id in validation_input.inventory_item_ids}
    actual_masks: list[list[bool]] = []
    wrong_instance = outside_safe = protected = uncertainty = 0
    boundary_damage = residue = 0
    dependencies_fresh = True
    for member in validation_input.members:
        actual = _load_mask(member.actual_changed_mask_png, original.size)
        ownership = _load_mask(member.instance_ownership_mask_png, original.size)
        safe = _load_mask(member.safe_edit_mask_png, original.size)
        protected_mask = _load_mask(member.protected_mask_png, original.size)
        uncertainty_mask = _load_mask(member.uncertainty_mask_png, original.size)
        actual_masks.append(actual)
        wrong_instance += _count_selected(actual, [not value for value in ownership])
        outside_safe += _count_selected(actual, [not value for value in safe])
        protected += _count_selected(actual, protected_mask)
        uncertainty += _count_selected(actual, uncertainty_mask)
        boundary_damage += member.boundary_damage_pixel_count
        residue += member.residue_pixel_count
        dependencies_fresh = dependencies_fresh and member.dependencies_fresh
        for item_id in member.inventory_item_ids:
            if item_id in target_counts:
                target_counts[item_id] += 1

    existing_counts: dict[str, int] = {}
    existing_nonblocking: dict[str, bool] = {}
    for item_id, _code, is_blocking in validation_input.existing_dispositions:
        existing_counts[item_id] = existing_counts.get(item_id, 0) + 1
        existing_nonblocking[item_id] = (
            existing_nonblocking.get(item_id, True) and not is_blocking
        )

    missing = 0
    duplicates = 0
    dispositions_unique = True
    for item_id, member_count in target_counts.items():
        disposition_count = existing_counts.get(item_id, 0)
        prospective_count = member_count + disposition_count
        if prospective_count == 0:
            missing += 1
        elif prospective_count > 1:
            duplicates += prospective_count - 1
        if prospective_count != 1:
            dispositions_unique = False
        if disposition_count and not existing_nonblocking.get(item_id, False):
            dispositions_unique = False

    pairwise_overlap = 0
    for left_index, left in enumerate(actual_masks):
        for right in actual_masks[left_index + 1 :]:
            pairwise_overlap += _count_selected(left, right)

    member_union = [False] * (original.width * original.height)
    for mask in actual_masks:
        member_union = [left or right for left, right in zip(member_union, mask, strict=True)]
    delta_matches = provided_delta == member_union and actual_combined_delta == member_union
    source_integrity = sha256(validation_input.original_png).hexdigest() == validation_input.expected_source_hash
    combined_integrity = sha256(validation_input.combined_png).hexdigest() == validation_input.expected_combined_hash
    inventory_complete = missing == 0
    passed = all(
        (
            inventory_complete,
            dispositions_unique,
            duplicates == 0,
            pairwise_overlap == 0,
            wrong_instance == 0,
            outside_safe == 0,
            protected == 0,
            uncertainty == 0,
            boundary_damage == 0,
            residue == 0,
            delta_matches,
            source_integrity,
            combined_integrity,
            dependencies_fresh,
        )
    )
    summary = {
        "inventory_complete": inventory_complete,
        "dispositions_unique": dispositions_unique,
        "missing_attribution_count": missing,
        "duplicate_attribution_count": duplicates,
        "pairwise_overlap_pixel_count": pairwise_overlap,
        "wrong_instance_write_pixel_count": wrong_instance,
        "outside_safe_pixel_count": outside_safe,
        "protected_pixel_count": protected,
        "uncertainty_pixel_count": uncertainty,
        "boundary_damage_pixel_count": boundary_damage,
        "residue_pixel_count": residue,
        "combined_delta_matches_member_union": delta_matches,
        "source_integrity_valid": source_integrity,
        "combined_integrity_valid": combined_integrity,
        "dependencies_fresh": dependencies_fresh,
    }
    return PageCleaningValidationResult(
        status="pass" if passed else "fail",
        inventory_complete=inventory_complete,
        dispositions_unique=dispositions_unique,
        missing_attribution_count=missing,
        duplicate_attribution_count=duplicates,
        pairwise_overlap_pixel_count=pairwise_overlap,
        wrong_instance_write_pixel_count=wrong_instance,
        outside_safe_pixel_count=outside_safe,
        protected_pixel_count=protected,
        uncertainty_pixel_count=uncertainty,
        boundary_damage_pixel_count=boundary_damage,
        residue_pixel_count=residue,
        combined_delta_matches_member_union=delta_matches,
        source_integrity_valid=source_integrity,
        combined_integrity_valid=combined_integrity,
        dependencies_fresh=dependencies_fresh,
        validator_summary=json.dumps(summary, sort_keys=True, separators=(",", ":")),
    )


def _load_image(payload: bytes) -> Image.Image:
    with Image.open(BytesIO(payload)) as image:
        image.load()
        return image.copy()


def _load_mask(payload: bytes, expected_size: tuple[int, int]) -> list[bool]:
    with Image.open(BytesIO(payload)) as image:
        image.load()
        if image.size != expected_size:
            raise ValueError("Mask dimensions must match the original image.")
        return [value > 0 for value in image.convert("L").getdata()]


def _require_same_image_contract(original: Image.Image, candidate: Image.Image) -> None:
    if candidate.size != original.size or candidate.mode != original.mode:
        raise ValueError("Candidate dimensions and mode must match the original image.")


def _encode_png(image: Image.Image) -> bytes:
    stream = BytesIO()
    image.save(stream, format="PNG", optimize=False, compress_level=9)
    return stream.getvalue()


def _encode_mask(mask: list[bool], size: tuple[int, int]) -> bytes:
    image = Image.new("L", size)
    image.putdata([255 if selected else 0 for selected in mask])
    return _encode_png(image)


def _count_selected(left: list[bool], right: list[bool]) -> int:
    return sum(
        left_selected and right_selected
        for left_selected, right_selected in zip(left, right, strict=True)
    )
