from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from manga_read_flow.cleaning.full_page import (
    CompositionMember,
    PageCleaningValidationInput,
    PageValidationMember,
    compose_full_page_cleaning,
    validate_full_page_cleaning,
)
from manga_read_flow.domain.artifacts import ArtifactSafetyMetadata

from manga_read_flow.persistence.full_page_cleaning_acceptance_repository import (
    FullPageCleaningAcceptanceCommand,
    FullPageCleaningBlockCommand,
    FullPageCleaningTransactionOutcome,
    CombinedCleaningCandidateDraft,
    CombinedCleaningCandidateMemberDraft,
    PageCleaningValidationDraft,
)


@dataclass(frozen=True)
class FullPageCleaningDecision:
    validation_status: str
    outcome: FullPageCleaningTransactionOutcome


@dataclass(frozen=True)
class FullPagePreparationMember:
    instance_cleaning_result_id: str
    bubble_instance_revision_id: str
    composition_key: str
    candidate_png: bytes
    actual_changed_mask_png: bytes
    actual_changed_artifact_id: str
    actual_changed_hash: str
    inventory_item_ids: tuple[str, ...]
    instance_ownership_mask_png: bytes
    safe_edit_mask_png: bytes
    protected_mask_png: bytes
    uncertainty_mask_png: bytes
    boundary_damage_pixel_count: int
    residue_pixel_count: int
    dependencies_fresh: bool


@dataclass(frozen=True)
class PrepareFullPageCleaningCommand:
    combined_cleaning_candidate_id: str
    page_cleaning_validation_record_id: str
    page_cleaning_run_id: str
    batch_id: str
    page_id: str
    source_artifact_id: str
    source_hash: str
    original_png: bytes
    inventory_item_ids: tuple[str, ...]
    composition_config_hash: str
    validation_fingerprint: str
    members: tuple[FullPagePreparationMember, ...]
    existing_dispositions: tuple[tuple[str, str, bool], ...] = ()


@dataclass(frozen=True)
class PreparedFullPageCleaning:
    combined_artifact_id: str
    combined_delta_artifact_id: str
    validation_evidence_artifact_id: str
    member_set_fingerprint: str
    validation_status: str


class FullPageCleaningPreparationService:
    """Compute outside SQLite, promote artifacts, then append durable ledger facts."""

    def __init__(self, *, artifact_service, acceptance_repository) -> None:
        self._artifact_service = artifact_service
        self._acceptance_repository = acceptance_repository

    def prepare(
        self, command: PrepareFullPageCleaningCommand
    ) -> PreparedFullPageCleaning:
        composed = compose_full_page_cleaning(
            command.original_png,
            tuple(
                CompositionMember(
                    member.instance_cleaning_result_id,
                    member.composition_key,
                    member.candidate_png,
                    member.actual_changed_mask_png,
                )
                for member in command.members
            ),
        )
        validation = validate_full_page_cleaning(
            PageCleaningValidationInput(
                original_png=command.original_png,
                expected_source_hash=command.source_hash,
                combined_png=composed.combined_png,
                expected_combined_hash=composed.combined_hash,
                combined_delta_mask_png=composed.combined_delta_mask_png,
                inventory_item_ids=command.inventory_item_ids,
                members=tuple(
                    PageValidationMember(
                        member.instance_cleaning_result_id,
                        member.inventory_item_ids,
                        member.actual_changed_mask_png,
                        member.instance_ownership_mask_png,
                        member.safe_edit_mask_png,
                        member.protected_mask_png,
                        member.uncertainty_mask_png,
                        member.boundary_damage_pixel_count,
                        member.residue_pixel_count,
                        member.dependencies_fresh,
                    )
                    for member in command.members
                ),
                existing_dispositions=command.existing_dispositions,
            )
        )

        with TemporaryDirectory(prefix="manga-read-flow-full-page-") as temporary:
            temporary_path = Path(temporary)
            combined_path = temporary_path / "combined.png"
            delta_path = temporary_path / "combined-delta.png"
            evidence_path = temporary_path / "page-validation.json"
            combined_path.write_bytes(composed.combined_png)
            delta_path.write_bytes(composed.combined_delta_mask_png)
            evidence_path.write_text(validation.validator_summary, encoding="utf-8")
            combined_artifact = self._artifact_service.register_stage_output(
                temp_path=combined_path,
                batch_id=command.batch_id,
                page_id=command.page_id,
                owner_type="page_cleaning_run",
                owner_id=command.page_cleaning_run_id,
                artifact_type="full_page_cleaned_candidate",
                source_stage="cleaning",
                retention_class="stage_output",
                safety=ArtifactSafetyMetadata(may_contain_original_image=True),
                dependency_hash=composed.member_set_fingerprint,
            )
            delta_artifact = self._artifact_service.register_stage_output(
                temp_path=delta_path,
                batch_id=command.batch_id,
                page_id=command.page_id,
                owner_type="page_cleaning_run",
                owner_id=command.page_cleaning_run_id,
                artifact_type="actual_changed_mask",
                source_stage="cleaning_validation",
                retention_class="successful_payload",
                dependency_hash=composed.member_set_fingerprint,
            )
            evidence_artifact = self._artifact_service.register_stage_json(
                temp_path=evidence_path,
                batch_id=command.batch_id,
                page_id=command.page_id,
                owner_type="page_cleaning_run",
                owner_id=command.page_cleaning_run_id,
                artifact_type="page_validation_evidence",
                source_stage="cleaning_validation",
                retention_class="successful_payload",
                dependency_hash=command.validation_fingerprint,
            )

        self._acceptance_repository.create_combined_candidate_with_members(
            CombinedCleaningCandidateDraft(
                command.combined_cleaning_candidate_id,
                command.page_cleaning_run_id,
                command.source_artifact_id,
                command.source_hash,
                combined_artifact.artifact_id,
                combined_artifact.file_hash,
                delta_artifact.artifact_id,
                delta_artifact.file_hash,
                command.composition_config_hash,
                composed.member_set_fingerprint,
            ),
            tuple(
                CombinedCleaningCandidateMemberDraft(
                    member.instance_cleaning_result_id,
                    member.bubble_instance_revision_id,
                    member.composition_key,
                    member.actual_changed_artifact_id,
                    member.actual_changed_hash,
                )
                for member in command.members
            ),
        )
        self._acceptance_repository.append_page_cleaning_validation(
            PageCleaningValidationDraft(
                command.page_cleaning_validation_record_id,
                command.page_cleaning_run_id,
                command.combined_cleaning_candidate_id,
                command.validation_fingerprint,
                validation.status,
                validation.inventory_complete,
                validation.dispositions_unique,
                validation.missing_attribution_count,
                validation.duplicate_attribution_count,
                validation.pairwise_overlap_pixel_count,
                validation.wrong_instance_write_pixel_count,
                validation.outside_safe_pixel_count,
                validation.protected_pixel_count,
                validation.uncertainty_pixel_count,
                validation.boundary_damage_pixel_count,
                validation.residue_pixel_count,
                validation.combined_delta_matches_member_union,
                validation.source_integrity_valid,
                validation.combined_integrity_valid,
                validation.dependencies_fresh,
                evidence_artifact.artifact_id,
                None,
                None,
                validation.validator_summary,
            )
        )
        return PreparedFullPageCleaning(
            combined_artifact.artifact_id,
            delta_artifact.artifact_id,
            evidence_artifact.artifact_id,
            composed.member_set_fingerprint,
            validation.status,
        )


class FullPageCleaningDecisionOrchestrator:
    """Choose the short acceptance or block UoW after external validation."""

    def __init__(self, *, project_uow) -> None:
        self._project_uow = project_uow

    def finalize(
        self,
        *,
        validation_status: str,
        acceptance_command: FullPageCleaningAcceptanceCommand | None,
        block_command: FullPageCleaningBlockCommand | None,
    ) -> FullPageCleaningDecision:
        if validation_status == "pass":
            if acceptance_command is None:
                raise ValueError("Passing validation requires an acceptance command.")
            outcome = self._project_uow.accept_page_cleaning_atomically(
                acceptance_command
            )
        elif validation_status == "fail":
            if block_command is None:
                raise ValueError("Failing validation requires a block command.")
            outcome = self._project_uow.block_page_cleaning_atomically(block_command)
        else:
            raise ValueError("Validation status must be pass or fail.")
        return FullPageCleaningDecision(validation_status, outcome)


__all__ = [
    "FullPageCleaningDecision",
    "FullPageCleaningDecisionOrchestrator",
    "FullPageCleaningPreparationService",
    "FullPagePreparationMember",
    "PrepareFullPageCleaningCommand",
    "PreparedFullPageCleaning",
]
