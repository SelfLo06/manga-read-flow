from __future__ import annotations


def accept_export_check(
    *,
    repositories,
    artifact_service,
    task,
    page,
    stage_result,
    build_command,
    build_blocked_command,
):
    readiness = repositories.readiness.get_page_export_readiness(
        page.page_id,
        profile_snapshot_id=task.profile_snapshot_id,
    )
    artifact_is_valid = False
    warning_artifact_is_valid = False
    if readiness.active_typeset_artifact_id is not None:
        report = artifact_service.validate_artifact(
            readiness.active_typeset_artifact_id,
            expected_use="export_check",
            active_reference="page.active_typeset_artifact_id",
        )
        artifact_is_valid = (
            readiness.active_typeset_artifact_type == "typeset_image"
            and readiness.active_typeset_storage_state == "present"
            and report.integrity_status == "valid"
        )
        warning_artifact_is_valid = (
            readiness.active_typeset_artifact_type
            in {"typeset_image", "typeset_preview_image"}
            and readiness.active_typeset_storage_state == "present"
            and report.integrity_status == "valid"
        )

    ready = (
        readiness.active_typeset_artifact_id is not None
        and artifact_is_valid
        and readiness.open_blocking_issue_count == 0
        and readiness.incomplete_text_block_count == 0
        and readiness.unresolved_warning_issue_count == 0
        and readiness.skipped_text_block_count == 0
    )
    if ready:
        return repositories.uow.accept_stage(
            build_command(
                task_id=task.task_id,
                task_status=task.status,
                current_stage=task.current_stage,
                page=page,
                stage_result=stage_result,
                decision_type="finish_ready_for_export",
                reason_code="export_readiness_passed",
                next_stage="finish_ready_for_export",
                task_terminal_status="succeeded",
                page_status="ready_for_export",
            )
        )

    warning_ready = (
        readiness.active_typeset_artifact_id is not None
        and warning_artifact_is_valid
        and readiness.open_blocking_issue_count == 0
        and readiness.incomplete_text_block_count == 0
        and (
            readiness.unresolved_warning_issue_count > 0
            or readiness.skipped_text_block_count > 0
        )
        and readiness.allow_warning_export
    )
    if warning_ready:
        return repositories.uow.accept_stage(
            build_command(
                task_id=task.task_id,
                task_status=task.status,
                current_stage=task.current_stage,
                page=page,
                stage_result=stage_result,
                decision_type="finish_ready_for_export_with_warnings",
                reason_code="export_readiness_passed_with_warnings",
                next_stage="finish_ready_for_export_with_warnings",
                task_terminal_status="succeeded_with_warnings",
                page_status="ready_for_export_with_warnings",
                linked_issue_ids=readiness.unresolved_issue_ids,
            )
        )

    if readiness.unresolved_issue_ids:
        return repositories.uow.accept_stage(
            build_command(
                task_id=task.task_id,
                task_status=task.status,
                current_stage=task.current_stage,
                page=page,
                stage_result=stage_result,
                decision_type="block",
                reason_code="export_readiness_blocked",
                next_stage="block",
                task_terminal_status="blocked",
                page_status="blocked",
                linked_issue_ids=readiness.unresolved_issue_ids,
            )
        )

    return repositories.uow.accept_stage(
        build_blocked_command(
            task_id=task.task_id,
            task_status=task.status,
            current_stage=task.current_stage,
            page_id=page.page_id,
            page=page,
            attempt_id=stage_result.attempt_id,
            reason_code="export_readiness_blocked",
            issue_type="export_readiness_blocked",
        )
    )
