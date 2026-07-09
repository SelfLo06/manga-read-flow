from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from manga_read_flow.domain.artifacts import ProcessingArtifactSnapshot
from manga_read_flow.persistence.repository_uow_core import (
    BatchSnapshot,
    ImportPageStateCommand,
    PageSnapshot,
)


@dataclass(frozen=True)
class ImportPageCommand:
    source_path: Path
    batch_name: str
    page_index: int
    batch_id: str | None = None
    page_id: str | None = None
    original_filename: str | None = None


@dataclass(frozen=True)
class ImportedPage:
    batch: BatchSnapshot
    page: PageSnapshot
    original_artifact: ProcessingArtifactSnapshot


class ImportPageCommitError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        original_artifact: ProcessingArtifactSnapshot,
    ) -> None:
        super().__init__(message)
        self.original_artifact = original_artifact


class ImportPageService:
    def __init__(self, *, project_id: str, repositories, artifact_service) -> None:
        self._project_id = project_id
        self._repositories = repositories
        self._artifact_service = artifact_service

    def import_page(self, command: ImportPageCommand) -> ImportedPage:
        batch_id = command.batch_id or f"batch-{uuid4()}"
        page_id = command.page_id or f"page-{uuid4()}"
        original_filename = command.original_filename or Path(command.source_path).name

        original_artifact = self._artifact_service.register_original_image(
            source_path=command.source_path,
            batch_id=batch_id,
            page_id=page_id,
            original_filename=original_filename,
        )

        try:
            imported = self._repositories.uow.import_page_original(
                ImportPageStateCommand(
                    batch_id=batch_id,
                    batch_name=command.batch_name,
                    page_id=page_id,
                    page_index=command.page_index,
                    original_filename=original_filename,
                    original_artifact_id=original_artifact.artifact_id,
                )
            )
        except Exception as exc:
            raise ImportPageCommitError(
                "Original artifact was registered, but Page import state did not commit.",
                original_artifact=original_artifact,
            ) from exc

        return ImportedPage(
            batch=imported.batch,
            page=imported.page,
            original_artifact=original_artifact,
        )
