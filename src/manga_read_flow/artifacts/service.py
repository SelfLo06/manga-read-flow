from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
from uuid import uuid4

from manga_read_flow.domain.artifacts import (
    ArtifactIntegrityReport,
    ArtifactSafetyMetadata,
    ProcessingArtifactSnapshot,
    RegisterArtifactMetadata,
)


class ArtifactRegistrationError(ValueError):
    """Raised when bytes cannot safely become an official artifact."""


class ArtifactValidationError(ValueError):
    """Raised when artifact metadata cannot be resolved safely."""


@dataclass(frozen=True)
class _ImageInspection:
    mime_type: str
    width: int | None
    height: int | None


class ArtifactService:
    _ALLOWED_MEDIA_TYPES = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }

    def __init__(
        self,
        *,
        project_id: str,
        project_workspace_path: Path | str,
        artifact_repository,
    ) -> None:
        self._project_id = project_id
        self._project_workspace_path = Path(project_workspace_path)
        self._artifact_repository = artifact_repository

    def register_original_image(
        self,
        *,
        source_path: Path | str,
        batch_id: str,
        page_id: str,
        original_filename: str | None = None,
    ) -> ProcessingArtifactSnapshot:
        source = Path(source_path)
        display_filename = original_filename or source.name
        _reject_unsafe_filename(display_filename)

        if not source.is_file():
            raise ArtifactRegistrationError(f"Original image source is not a file: {source}")

        suffix = Path(display_filename).suffix.lower()
        expected_mime_type = self._ALLOWED_MEDIA_TYPES.get(suffix)
        if expected_mime_type is None:
            raise ArtifactRegistrationError(
                f"Unsupported original image extension: {suffix or '<none>'}"
            )

        _inspect_image(source, expected_mime_type)
        artifact_id = f"artifact-{uuid4()}"
        relative_path = self._original_relative_path(
            artifact_id=artifact_id,
            original_filename=display_filename,
        )
        destination = self._resolve_project_relative_path(relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _copy_without_overwrite(source, destination)
        try:
            inspection = _inspect_image(destination, expected_mime_type)
        except ArtifactRegistrationError:
            destination.unlink(missing_ok=True)
            raise

        byte_size = destination.stat().st_size
        file_hash = _sha256_file(destination)

        return self._artifact_repository.register_artifact(
            RegisterArtifactMetadata(
                artifact_id=artifact_id,
                batch_id=batch_id,
                page_id=page_id,
                owner_type="page",
                owner_id=page_id,
                artifact_type="original_image",
                source_stage="import",
                relative_path=relative_path,
                file_hash=file_hash,
                hash_algorithm="sha256",
                byte_size=byte_size,
                mime_type=inspection.mime_type,
                width=inspection.width,
                height=inspection.height,
                retention_class="permanent_original",
                storage_state="present",
                safety=ArtifactSafetyMetadata(may_contain_original_image=True),
            )
        )

    def register_stage_output(
        self,
        *,
        temp_path: Path | str,
        batch_id: str | None,
        page_id: str | None,
        owner_type: str,
        owner_id: str,
        artifact_type: str,
        source_stage: str,
        media_type: str | None = None,
        retention_class: str = "stage_output",
        safety: ArtifactSafetyMetadata | None = None,
    ) -> ProcessingArtifactSnapshot:
        source = Path(temp_path)
        if not source.is_file():
            raise ArtifactRegistrationError("Stage output temp file is not available.")

        suffix = source.suffix.lower()
        expected_mime_type = media_type or self._ALLOWED_MEDIA_TYPES.get(suffix)
        if expected_mime_type is None or expected_mime_type not in set(
            self._ALLOWED_MEDIA_TYPES.values()
        ):
            raise ArtifactRegistrationError(
                f"Unsupported stage output media type: {expected_mime_type or '<none>'}"
            )

        _inspect_image(source, expected_mime_type)
        artifact_id = f"artifact-{uuid4()}"
        relative_path = self._stage_relative_path(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            source_stage=source_stage,
            suffix=suffix,
        )
        destination = self._resolve_project_relative_path(relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _copy_without_overwrite(source, destination)
        try:
            inspection = _inspect_image(destination, expected_mime_type)
        except ArtifactRegistrationError:
            destination.unlink(missing_ok=True)
            raise

        return self._artifact_repository.register_artifact(
            RegisterArtifactMetadata(
                artifact_id=artifact_id,
                batch_id=batch_id,
                page_id=page_id,
                owner_type=owner_type,
                owner_id=owner_id,
                artifact_type=artifact_type,
                source_stage=source_stage,
                relative_path=relative_path,
                file_hash=_sha256_file(destination),
                hash_algorithm="sha256",
                byte_size=destination.stat().st_size,
                mime_type=inspection.mime_type,
                width=inspection.width,
                height=inspection.height,
                retention_class=retention_class,
                storage_state="present",
                safety=safety or ArtifactSafetyMetadata(),
            )
        )

    def register_stage_image(
        self,
        *,
        source_path: Path | str,
        batch_id: str,
        page_id: str,
        stage: str,
        artifact_type: str,
        retention_class: str,
        safety: ArtifactSafetyMetadata,
    ) -> ProcessingArtifactSnapshot:
        return self.register_stage_output(
            temp_path=source_path,
            batch_id=batch_id,
            page_id=page_id,
            owner_type="page",
            owner_id=page_id,
            artifact_type=artifact_type,
            source_stage=stage,
            retention_class=retention_class,
            safety=safety,
        )

    def validate_artifact(
        self,
        artifact_id: str,
        *,
        expected_use: str,
        active_reference: str | None = None,
    ) -> ArtifactIntegrityReport:
        artifact = self._artifact_repository.get_artifact(artifact_id)
        try:
            artifact_path = self._resolve_project_relative_path(artifact.relative_path)
        except ArtifactValidationError:
            self._artifact_repository.update_storage_state(
                artifact_id=artifact.artifact_id,
                storage_state="missing",
            )
            return _integrity_report(
                artifact,
                expected_use=expected_use,
                active_reference=active_reference,
                observed_state="missing",
                integrity_status="inaccessible",
                observed_hash=None,
                evidence_summary="artifact path is outside the project workspace",
            )

        if artifact.storage_state in {"metadata_only_cleaned", "moved_to_trash", "deleted"}:
            return _integrity_report(
                artifact,
                expected_use=expected_use,
                active_reference=active_reference,
                observed_state=artifact.storage_state,
                integrity_status=artifact.storage_state,
                observed_hash=None,
                evidence_summary=f"artifact storage state is {artifact.storage_state}",
            )

        if not artifact_path.is_file():
            self._artifact_repository.update_storage_state(
                artifact_id=artifact.artifact_id,
                storage_state="missing",
            )
            return _integrity_report(
                artifact,
                expected_use=expected_use,
                active_reference=active_reference,
                observed_state="missing",
                integrity_status="missing_path",
                observed_hash=None,
                evidence_summary="registered artifact file is missing",
            )

        observed_hash = _sha256_file(artifact_path)
        if observed_hash != artifact.file_hash:
            self._artifact_repository.update_storage_state(
                artifact_id=artifact.artifact_id,
                storage_state="missing",
            )
            return _integrity_report(
                artifact,
                expected_use=expected_use,
                active_reference=active_reference,
                observed_state="missing",
                integrity_status="hash_mismatch",
                observed_hash=observed_hash,
                evidence_summary="registered artifact hash does not match file bytes",
            )

        return _integrity_report(
            artifact,
            expected_use=expected_use,
            active_reference=active_reference,
            observed_state="present",
            integrity_status="valid",
            observed_hash=observed_hash,
            evidence_summary="artifact file exists and hash validates",
        )

    def _original_relative_path(self, *, artifact_id: str, original_filename: str) -> str:
        suffix = Path(original_filename).suffix.lower()
        stem = _safe_stem(Path(original_filename).stem)
        path = PurePosixPath("originals", f"{stem}-{artifact_id}{suffix}")
        return path.as_posix()

    def _stage_relative_path(
        self,
        *,
        artifact_id: str,
        artifact_type: str,
        source_stage: str,
        suffix: str,
    ) -> str:
        safe_stage = _safe_stem(source_stage)
        safe_artifact_type = _safe_stem(artifact_type)
        path = PurePosixPath(
            "artifacts",
            safe_stage,
            f"{safe_artifact_type}-{artifact_id}{suffix}",
        )
        return path.as_posix()

    def _resolve_project_relative_path(self, relative_path: str) -> Path:
        path = PurePosixPath(relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise ArtifactValidationError("Artifact path must be project-relative.")

        resolved = (self._project_workspace_path / Path(*path.parts)).resolve(strict=False)
        workspace = self._project_workspace_path.resolve(strict=False)
        try:
            resolved.relative_to(workspace)
        except ValueError as exc:
            raise ArtifactValidationError(
                "Artifact path must remain under the project workspace."
            ) from exc
        return resolved


def _integrity_report(
    artifact: ProcessingArtifactSnapshot,
    *,
    expected_use: str,
    active_reference: str | None,
    observed_state: str,
    integrity_status: str,
    observed_hash: str | None,
    evidence_summary: str,
) -> ArtifactIntegrityReport:
    return ArtifactIntegrityReport(
        artifact_id=artifact.artifact_id,
        artifact_type=artifact.artifact_type,
        expected_use=expected_use,
        observed_state=observed_state,
        integrity_status=integrity_status,
        expected_hash=artifact.file_hash,
        observed_hash=observed_hash,
        relative_path=artifact.relative_path,
        active_reference=active_reference,
        rebuildability_hint="non_rebuildable"
        if artifact.artifact_type == "original_image"
        else "unknown",
        evidence_summary=evidence_summary,
    )


def _reject_unsafe_filename(filename: str) -> None:
    normalized = filename.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or len(path.parts) != 1
        or path.name in {"", ".", ".."}
        or ".." in path.parts
    ):
        raise ArtifactRegistrationError("Original filename must not contain path traversal.")


def _safe_stem(stem: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return safe or "original"


def _inspect_image(path: Path, expected_mime_type: str) -> _ImageInspection:
    header = path.read_bytes()[:64]

    if expected_mime_type == "image/png":
        if not header.startswith(b"\x89PNG\r\n\x1a\n") or header[12:16] != b"IHDR":
            raise ArtifactRegistrationError("Invalid PNG original image.")
        width, height = struct.unpack(">II", header[16:24])
        if width <= 0 or height <= 0:
            raise ArtifactRegistrationError("Invalid PNG dimensions.")
        return _ImageInspection(mime_type=expected_mime_type, width=width, height=height)

    if expected_mime_type == "image/jpeg":
        if not header.startswith(b"\xff\xd8"):
            raise ArtifactRegistrationError("Invalid JPEG original image.")
        return _ImageInspection(mime_type=expected_mime_type, width=None, height=None)

    if expected_mime_type == "image/webp":
        if not (header.startswith(b"RIFF") and header[8:12] == b"WEBP"):
            raise ArtifactRegistrationError("Invalid WebP original image.")
        return _ImageInspection(mime_type=expected_mime_type, width=None, height=None)

    raise ArtifactRegistrationError(f"Unsupported media type: {expected_mime_type}")


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_without_overwrite(source: Path, destination: Path) -> None:
    try:
        with source.open("rb") as source_file, destination.open("xb") as destination_file:
            shutil.copyfileobj(source_file, destination_file)
    except FileExistsError as exc:
        raise ArtifactRegistrationError(
            f"Official artifact path already exists: {destination}"
        ) from exc
