from __future__ import annotations

from dataclasses import dataclass, field


CLASSIFICATION_VERSION = "quality-check-v0.1"


@dataclass(frozen=True)
class QualityCheckInput:
    stage: str
    target_type: str
    target_id: str
    page_id: str | None = None
    batch_id: str | None = None
    text_block_ids: tuple[str, ...] = ()
    provider_outcome: str | None = None
    error_kind: str | None = None
    error_code: str | None = None
    is_provider_refusal: bool = False
    workflow_attempt_id: str | None = None
    tool_run_id: str | None = None
    input_hash: str | None = None
    config_hash: str | None = None
    candidate_outputs: dict[str, object] = field(default_factory=dict)
    registered_artifact_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class IssueDraft:
    target_type: str
    target_id: str
    discovered_stage: str
    root_stage: str
    issue_type: str
    error_code: str
    severity: str
    is_blocking: bool
    status: str
    message_key: str
    suggested_action_key: str
    batch_id: str | None = None
    page_id: str | None = None
    text_block_id: str | None = None
    message_params: dict[str, object] = field(default_factory=dict)
    related_attempt_id: str | None = None
    related_tool_run_id: str | None = None
    related_artifact_id: str | None = None
    applies_to_result_id: str | None = None
    input_hash: str | None = None
    config_hash: str | None = None
    dedupe_key: str = ""


@dataclass(frozen=True)
class QualityCheckSummary:
    issue_count: int
    warning_count: int
    error_count: int
    blocking_count: int
    has_blocking_issue: bool
    max_severity: str | None
    dedupe_keys: tuple[str, ...]


@dataclass(frozen=True)
class QualityCheckReport:
    stage: str
    target_type: str
    target_id: str
    output_integrity: str
    issue_drafts: tuple[IssueDraft, ...]
    summary: QualityCheckSummary
    classification_version: str = CLASSIFICATION_VERSION


class QualityCheckService:
    def check(self, check_input: QualityCheckInput) -> QualityCheckReport:
        drafts = _issue_drafts(check_input)
        return QualityCheckReport(
            stage=check_input.stage,
            target_type=check_input.target_type,
            target_id=check_input.target_id,
            output_integrity=_output_integrity(check_input, drafts),
            issue_drafts=drafts,
            summary=_summary(drafts),
        )

    def check_grouping(self, check_input):
        from manga_read_flow.quality.grouping_check import GroupingCheck

        return GroupingCheck().evaluate(check_input)


def _issue_drafts(check_input: QualityCheckInput) -> tuple[IssueDraft, ...]:
    if check_input.is_provider_refusal or check_input.error_kind == "provider_refusal":
        return (_provider_refusal_issue(check_input),)

    if (
        check_input.stage == "translation"
        and check_input.error_code
        in {"translation_invalid_json", "translation_schema_invalid"}
    ):
        return (_invalid_translation_issue(check_input),)

    if check_input.stage == "translation":
        missing_targets = _missing_translation_targets(check_input)
        if missing_targets:
            return tuple(
                _missing_translation_issue(check_input, text_block_id)
                for text_block_id in missing_targets
            )

    if check_input.stage == "cleaning" and _has_cleaning_skip(check_input):
        return (_cleaning_skip_issue(check_input),)

    if check_input.stage == "cleaning":
        cleaning_issues = _cleaning_validation_issues(check_input)
        if cleaning_issues:
            return cleaning_issues

    if check_input.stage == "typesetting" and _has_typesetting_overflow(check_input):
        return (_typesetting_overflow_issue(check_input),)

    if check_input.error_code == "artifact_registration_failed":
        return (_artifact_registration_issue(check_input),)

    return ()


def _cleaning_validation_issues(check_input: QualityCheckInput) -> tuple[IssueDraft, ...]:
    evidence = check_input.candidate_outputs
    related_artifact_id = evidence.get("primary_evidence_artifact_id")
    if related_artifact_id is not None:
        related_artifact_id = str(related_artifact_id)
    rules = (
        ("visible_residue", "cleaning_residue", "cleaning_residue", "cleaning.residue"),
        ("outside_safe_edit", "structure_damage", "outside_safe_edit", "cleaning.structure_damage"),
        ("protected_damage", "structure_damage", "protected_structure_damage", "cleaning.structure_damage"),
        ("uncertainty_damage", "structure_damage", "uncertainty_structure_damage", "cleaning.structure_damage"),
        ("background_inconsistency", "background_inconsistency", "cleaning_background_inconsistency", "cleaning.background_inconsistency"),
        ("ordinary_bubble_false_exclusion", "ordinary_bubble_false_exclusion", "cleaning_eligibility_unexplained", "cleaning.eligibility_exclusion"),
        ("page_scope_incomplete", "cleaning_scope_incomplete", "cleaning_scope_incomplete", "cleaning.scope_incomplete"),
    )
    drafts = [
        _draft(
            check_input,
            target_type=check_input.target_type,
            target_id=check_input.target_id,
            discovered_stage="cleaning",
            root_stage="cleaning",
            issue_type=issue_type,
            error_code=error_code,
            severity="blocking",
            is_blocking=True,
            message_key=message_key,
            suggested_action_key="action.review_skip_or_retry_cleaning",
            related_artifact_id=related_artifact_id,
        )
        for key, issue_type, error_code, message_key in rules
        if bool(evidence.get(key))
    ]
    for text_block_id in evidence.get("incomplete_text_block_ids", ()):
        drafts.append(
            _draft(
                check_input,
                target_type="text_block",
                target_id=str(text_block_id),
                text_block_id=str(text_block_id),
                discovered_stage="cleaning",
                root_stage="cleaning",
                issue_type="cleaning_input_incomplete",
                error_code="required_support_unsafe",
                severity="blocking",
                is_blocking=True,
                message_key="cleaning.input_incomplete",
                suggested_action_key="action.review_skip_or_retry_cleaning",
                related_artifact_id=related_artifact_id,
            )
        )
    if evidence.get("required_support_incomplete") and not evidence.get(
        "incomplete_text_block_ids"
    ):
        drafts.append(
            _draft(
                check_input,
                target_type=check_input.target_type,
                target_id=check_input.target_id,
                discovered_stage="cleaning",
                root_stage="cleaning",
                issue_type="cleaning_input_incomplete",
                error_code="required_support_unsafe",
                severity="blocking",
                is_blocking=True,
                message_key="cleaning.input_incomplete",
                suggested_action_key="action.review_skip_or_retry_cleaning",
                related_artifact_id=related_artifact_id,
            )
        )
    return tuple(drafts)


def _provider_refusal_issue(check_input: QualityCheckInput) -> IssueDraft:
    message_key = (
        "provider.refused.translation"
        if check_input.stage == "translation"
        else "provider.refused"
    )
    return _draft(
        check_input,
        target_type=check_input.target_type,
        target_id=check_input.target_id,
        discovered_stage=check_input.stage,
        root_stage="provider_policy",
        issue_type="provider_refusal",
        error_code=check_input.error_code or "translation_provider_refused",
        severity="error",
        is_blocking=True,
        message_key=message_key,
        suggested_action_key="action.use_allowed_alternative_or_manual",
    )


def _invalid_translation_issue(check_input: QualityCheckInput) -> IssueDraft:
    return _draft(
        check_input,
        target_type=check_input.target_type,
        target_id=check_input.target_id,
        discovered_stage="translation",
        root_stage="translation",
        issue_type="stage_output_invalid",
        error_code=check_input.error_code or "translation_invalid_json",
        severity="error",
        is_blocking=True,
        message_key="translation.invalid_output",
        suggested_action_key="action.retry_or_manual_translate",
    )


def _missing_translation_issue(
    check_input: QualityCheckInput,
    text_block_id: str,
) -> IssueDraft:
    return _draft(
        check_input,
        target_type="text_block",
        target_id=text_block_id,
        text_block_id=text_block_id,
        discovered_stage="translation_check",
        root_stage="translation",
        issue_type="translation_missing_block",
        error_code="translation_missing_text_block",
        severity="error",
        is_blocking=True,
        message_key="translation.missing_text_block",
        suggested_action_key="action.retry_or_manual_translate",
    )


def _cleaning_skip_issue(check_input: QualityCheckInput) -> IssueDraft:
    return _draft(
        check_input,
        target_type=check_input.target_type,
        target_id=check_input.target_id,
        discovered_stage="cleaning",
        root_stage="cleaning",
        issue_type="cleaning_skipped_complex_region",
        error_code="cleaning_complex_background",
        severity="warning",
        is_blocking=False,
        message_key="cleaning.skipped_complex_background",
        suggested_action_key="action.review_skip_or_retry_cleaning",
    )


def _typesetting_overflow_issue(check_input: QualityCheckInput) -> IssueDraft:
    related_artifact_id = (
        check_input.registered_artifact_ids[0]
        if check_input.registered_artifact_ids
        else None
    )
    return _draft(
        check_input,
        target_type=check_input.target_type,
        target_id=check_input.target_id,
        discovered_stage="typesetting",
        root_stage="typesetting",
        issue_type="typesetting_overflow",
        error_code="typeset_overflow",
        severity="warning",
        is_blocking=False,
        message_key="typesetting.overflow",
        suggested_action_key="action.shorten_or_review_layout",
        related_artifact_id=related_artifact_id,
    )


def _artifact_registration_issue(check_input: QualityCheckInput) -> IssueDraft:
    return _draft(
        check_input,
        target_type=check_input.target_type,
        target_id=check_input.target_id,
        discovered_stage=check_input.stage,
        root_stage="artifact",
        issue_type="artifact_unavailable",
        error_code="artifact_registration_failed",
        severity="blocking",
        is_blocking=True,
        message_key="artifact.registration_failed",
        suggested_action_key="action.rebuild_or_restore_artifact",
    )


def _draft(
    check_input: QualityCheckInput,
    *,
    target_type: str,
    target_id: str,
    discovered_stage: str,
    root_stage: str,
    issue_type: str,
    error_code: str,
    severity: str,
    is_blocking: bool,
    message_key: str,
    suggested_action_key: str,
    text_block_id: str | None = None,
    related_artifact_id: str | None = None,
) -> IssueDraft:
    scope_page_id = check_input.page_id
    return IssueDraft(
        target_type=target_type,
        target_id=target_id,
        batch_id=check_input.batch_id,
        page_id=scope_page_id,
        text_block_id=text_block_id,
        discovered_stage=discovered_stage,
        root_stage=root_stage,
        issue_type=issue_type,
        error_code=error_code,
        severity=severity,
        is_blocking=is_blocking,
        status="open",
        message_key=message_key,
        message_params={},
        suggested_action_key=suggested_action_key,
        related_attempt_id=check_input.workflow_attempt_id,
        related_tool_run_id=check_input.tool_run_id,
        related_artifact_id=related_artifact_id,
        input_hash=check_input.input_hash,
        config_hash=check_input.config_hash,
        dedupe_key=(
            f"{scope_page_id or check_input.target_id}:"
            f"{target_type}:{target_id}:{issue_type}:{error_code}"
        ),
    )


def _missing_translation_targets(check_input: QualityCheckInput) -> tuple[str, ...]:
    explicit_missing = check_input.candidate_outputs.get("missing_targets")
    if explicit_missing is not None:
        return tuple(str(target_id) for target_id in explicit_missing)

    translations = check_input.candidate_outputs.get("translations", ())
    returned_ids = {
        str(item.get("text_block_id"))
        for item in translations
        if isinstance(item, dict) and item.get("text_block_id") is not None
    }
    return tuple(
        text_block_id
        for text_block_id in check_input.text_block_ids
        if text_block_id not in returned_ids
    )


def _has_cleaning_skip(check_input: QualityCheckInput) -> bool:
    if check_input.error_code == "cleaning_complex_background":
        return True
    block_results = check_input.candidate_outputs.get("block_results", ())
    return any(
        isinstance(result, dict)
        and (
            result.get("status_hint") == "cannot_clean"
            or result.get("reason_code") == "cleaning_complex_background"
        )
        for result in block_results
    )


def _has_typesetting_overflow(check_input: QualityCheckInput) -> bool:
    if check_input.error_code == "typeset_overflow":
        return True
    layout_results = check_input.candidate_outputs.get("layout_results", ())
    return any(
        isinstance(result, dict)
        and (result.get("overflow") is True or result.get("fitted") is False)
        for result in layout_results
    )


def _output_integrity(
    check_input: QualityCheckInput,
    drafts: tuple[IssueDraft, ...],
) -> str:
    if check_input.is_provider_refusal:
        return "refused"
    if check_input.provider_outcome == "partial_success":
        if check_input.stage == "cleaning":
            return "skipped"
        return "partial"
    if check_input.provider_outcome == "invalid_output":
        return "invalid"
    if drafts and all(not draft.is_blocking for draft in drafts):
        return "usable_with_warning"
    return "complete" if not drafts else "invalid"


def _summary(drafts: tuple[IssueDraft, ...]) -> QualityCheckSummary:
    severity_order = {"info": 0, "warning": 1, "error": 2, "blocking": 3}
    max_severity = None
    if drafts:
        max_severity = max(
            (draft.severity for draft in drafts),
            key=lambda severity: severity_order[severity],
        )
    return QualityCheckSummary(
        issue_count=len(drafts),
        warning_count=sum(1 for draft in drafts if draft.severity == "warning"),
        error_count=sum(1 for draft in drafts if draft.severity == "error"),
        blocking_count=sum(1 for draft in drafts if draft.is_blocking),
        has_blocking_issue=any(draft.is_blocking for draft in drafts),
        max_severity=max_severity,
        dedupe_keys=tuple(draft.dedupe_key for draft in drafts),
    )
