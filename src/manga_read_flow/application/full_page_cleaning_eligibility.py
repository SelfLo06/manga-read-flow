"""Versioned eligibility decisions for MVP-1 full-page Cleaning.

The decision is intentionally narrower than an E1 approval.  It converts a
frozen target class, historical classifier signal, and current pixel evidence
into a reproducible eligibility record.  In particular, an old instance-level
E3 signal cannot by itself become a final unsupported disposition once the
current required support has no protected or uncertainty intersection.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


ELIGIBILITY_POLICY_VERSION = "mvp1-full-page-cleaning-eligibility-v1"


@dataclass(frozen=True)
class FullPageEligibilityInput:
    target_class: str
    historical_candidate_risk: str
    required_pixels: int
    safe_covered_required_pixels: int
    required_protected_overlap_pixels: int
    required_uncertainty_overlap_pixels: int
    support_completeness: str
    bubble_instance_revision_id: str
    text_segment_revision_id: str
    evidence_source_revision: str
    classifier_policy_version: str
    profile_identity: str
    config_identity: str


@dataclass(frozen=True)
class FullPageEligibilityDecision:
    eligibility: str
    support_completeness: str
    reason_code: str
    classifier_policy_version: str
    eligibility_decision_version: str
    evidence_source_revision: str
    dependency_fingerprint: str
    evidence_summary: dict[str, object]


def decide_full_page_cleaning_eligibility(
    decision_input: FullPageEligibilityInput,
) -> FullPageEligibilityDecision:
    """Return a deterministic, conservative eligibility decision.

    ``E1`` remains an execution eligibility only.  A historical E3 with a
    complete current pixel support that is fully safe is deliberately mapped to
    ``REVIEW``: the evidence disproves the old *instance-level* E3 rationale,
    but does not by itself approve running the Cleaner.
    """
    _validate(decision_input)
    unsafe_required_pixels = (
        decision_input.required_pixels - decision_input.safe_covered_required_pixels
    )
    intersects_guard = (
        decision_input.required_protected_overlap_pixels > 0
        or decision_input.required_uncertainty_overlap_pixels > 0
    )
    target_class = decision_input.target_class
    historical_risk = decision_input.historical_candidate_risk

    if target_class in {"sfx_or_free_text", "sign_or_scene_text_review", "review"}:
        eligibility = "REVIEW"
        reason_code = "target_class_requires_review"
    elif historical_risk == "E3" and intersects_guard:
        eligibility = "E3"
        reason_code = "pixel_level_protected_or_uncertainty_conflict"
    elif historical_risk == "E3":
        eligibility = "REVIEW"
        reason_code = "pixel_level_evidence_requires_review"
    elif historical_risk == "E1":
        eligibility = "E1"
        reason_code = (
            "supported_e1"
            if decision_input.support_completeness == "COMPLETE"
            else "required_text_not_safely_editable"
        )
    else:
        eligibility = "REVIEW"
        reason_code = "historical_risk_requires_review"

    summary = {
        "target_class": target_class,
        "historical_candidate_risk": historical_risk,
        "required_pixels": decision_input.required_pixels,
        "safe_covered_required_pixels": decision_input.safe_covered_required_pixels,
        "unsafe_required_pixels": unsafe_required_pixels,
        "required_protected_overlap_pixels": decision_input.required_protected_overlap_pixels,
        "required_uncertainty_overlap_pixels": decision_input.required_uncertainty_overlap_pixels,
        "support_completeness": decision_input.support_completeness,
        "instance_revision": decision_input.bubble_instance_revision_id,
        "segment_revision": decision_input.text_segment_revision_id,
        "evidence_source_revision": decision_input.evidence_source_revision,
        "classifier_policy_version": decision_input.classifier_policy_version,
        "eligibility_decision_version": ELIGIBILITY_POLICY_VERSION,
        "profile_identity": decision_input.profile_identity,
        "config_identity": decision_input.config_identity,
        "reason_code": reason_code,
    }
    fingerprint = sha256(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return FullPageEligibilityDecision(
        eligibility=eligibility,
        support_completeness=decision_input.support_completeness,
        reason_code=reason_code,
        classifier_policy_version=decision_input.classifier_policy_version,
        eligibility_decision_version=ELIGIBILITY_POLICY_VERSION,
        evidence_source_revision=decision_input.evidence_source_revision,
        dependency_fingerprint=fingerprint,
        evidence_summary=summary,
    )


def _validate(value: FullPageEligibilityInput) -> None:
    if value.target_class not in {
        "ordinary_dialogue",
        "narration",
        "sign_or_scene_text_review",
        "sfx_or_free_text",
        "review",
        "unsupported_excluded",
    }:
        raise ValueError(f"Unsupported full-page Cleaning target class: {value.target_class}")
    if value.historical_candidate_risk not in {"E1", "E2", "E3", "REVIEW"}:
        raise ValueError(f"Unsupported historical candidate risk: {value.historical_candidate_risk}")
    if value.support_completeness not in {"COMPLETE", "INCOMPLETE_REVIEW"}:
        raise ValueError(f"Unsupported support completeness: {value.support_completeness}")
    counts = (
        value.required_pixels,
        value.safe_covered_required_pixels,
        value.required_protected_overlap_pixels,
        value.required_uncertainty_overlap_pixels,
    )
    if any(count < 0 for count in counts):
        raise ValueError("Eligibility evidence counts cannot be negative.")
    if value.safe_covered_required_pixels > value.required_pixels:
        raise ValueError("Safe covered required pixels cannot exceed required pixels.")


__all__ = [
    "ELIGIBILITY_POLICY_VERSION",
    "FullPageEligibilityDecision",
    "FullPageEligibilityInput",
    "decide_full_page_cleaning_eligibility",
]
