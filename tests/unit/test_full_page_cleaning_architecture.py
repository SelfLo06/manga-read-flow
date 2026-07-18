from __future__ import annotations

from pathlib import Path
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace

from PIL import Image

from manga_read_flow.application.full_page_cleaning import (
    FullPageCleaningDecisionOrchestrator,
    FullPageCleaningPreparationService,
    FullPagePreparationMember,
    PrepareFullPageCleaningCommand,
)
from manga_read_flow.persistence.full_page_cleaning_acceptance_repository import (
    FullPageCleaningTransactionOutcome,
)


class _RecordingUow:
    def __init__(self):
        self.calls = []

    def accept_page_cleaning_atomically(self, command):
        self.calls.append(("accept", command))
        return FullPageCleaningTransactionOutcome(True, "ACCEPTED")

    def block_page_cleaning_atomically(self, command):
        self.calls.append(("block", command))
        return FullPageCleaningTransactionOutcome(True, "BLOCKED")


def test_orchestrator_alone_selects_acceptance_or_block_transaction():
    uow = _RecordingUow()
    orchestrator = FullPageCleaningDecisionOrchestrator(project_uow=uow)

    accepted = orchestrator.finalize(
        validation_status="pass", acceptance_command="accept-command", block_command=None
    )
    blocked = orchestrator.finalize(
        validation_status="fail", acceptance_command=None, block_command="block-command"
    )

    assert accepted.outcome.result_code == "ACCEPTED"
    assert blocked.outcome.result_code == "BLOCKED"
    assert uow.calls == [
        ("accept", "accept-command"),
        ("block", "block-command"),
    ]


def test_composer_validator_and_provider_keep_persistence_decisions_outside():
    composition_source = Path(
        "src/manga_read_flow/cleaning/full_page.py"
    ).read_text(encoding="utf-8")
    provider_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("src/manga_read_flow/providers").glob("*.py")
    )
    single_page_source = Path(
        "src/manga_read_flow/application/clean_single_page.py"
    ).read_text(encoding="utf-8")

    assert "sqlite3" not in composition_source
    assert "persistence" not in composition_source
    assert "active_cleaned_artifact_id" not in composition_source
    assert "FullPageCleaningAcceptance" not in provider_sources
    assert "accept_page_cleaning_atomically" not in provider_sources
    assert "FullPageCleaningDecisionOrchestrator" not in single_page_source


def test_preparation_promotes_artifacts_before_persisting_candidate_and_validation():
    events = []
    artifact_service = _RecordingArtifactService(events)
    repository = _RecordingAcceptanceRepository(events)
    service = FullPageCleaningPreparationService(
        artifact_service=artifact_service,
        acceptance_repository=repository,
    )
    original = _rgb([0, 0])
    candidate = _rgb([80, 0])
    selected = _mask({0})
    empty = _mask(set())

    prepared = service.prepare(
        PrepareFullPageCleaningCommand(
            combined_cleaning_candidate_id="candidate-page",
            page_cleaning_validation_record_id="validation-page",
            page_cleaning_run_id="run",
            batch_id="batch",
            page_id="page",
            source_artifact_id="original",
            source_hash=sha256(original).hexdigest(),
            original_png=original,
            inventory_item_ids=("item",),
            composition_config_hash="config",
            validation_fingerprint="validation-fingerprint",
            members=(
                FullPagePreparationMember(
                    "result",
                    "instance-revision",
                    "01/result",
                    candidate,
                    selected,
                    "actual-artifact",
                    "actual-hash",
                    ("item",),
                    selected,
                    selected,
                    empty,
                    empty,
                    0,
                    0,
                    True,
                ),
            ),
        )
    )

    assert prepared.validation_status == "pass"
    assert [event[0] for event in events] == [
        "promote-image",
        "promote-image",
        "promote-json",
        "persist-candidate",
        "persist-validation",
    ]


class _RecordingArtifactService:
    def __init__(self, events):
        self.events = events
        self.index = 0

    def register_stage_output(self, **kwargs):
        payload = Path(kwargs["temp_path"]).read_bytes()
        self.index += 1
        self.events.append(("promote-image", kwargs["artifact_type"]))
        return SimpleNamespace(
            artifact_id=f"artifact-{self.index}",
            file_hash=sha256(payload).hexdigest(),
        )

    def register_stage_json(self, **kwargs):
        payload = Path(kwargs["temp_path"]).read_bytes()
        self.index += 1
        self.events.append(("promote-json", kwargs["artifact_type"]))
        return SimpleNamespace(
            artifact_id=f"artifact-{self.index}",
            file_hash=sha256(payload).hexdigest(),
        )


class _RecordingAcceptanceRepository:
    def __init__(self, events):
        self.events = events

    def create_combined_candidate_with_members(self, candidate, members):
        self.events.append(("persist-candidate", candidate, members))

    def append_page_cleaning_validation(self, validation):
        self.events.append(("persist-validation", validation))


def _rgb(values):
    image = Image.new("RGB", (len(values), 1))
    image.putdata([(value, value, value) for value in values])
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _mask(indexes):
    image = Image.new("L", (2, 1))
    image.putdata([255 if index in indexes else 0 for index in range(2)])
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()
