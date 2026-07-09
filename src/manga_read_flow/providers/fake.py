from __future__ import annotations

import struct
import zlib

from manga_read_flow.domain.provider_contracts import (
    ProviderError,
    ProviderOutcome,
    ProviderRequest,
    ProviderResult,
    ProviderTempFileRef,
)


class FakeProvider:
    provider_name = "FakeProvider"
    model_id = "fake-model-v0"
    tool_name = "fake-provider"
    tool_version = "0.1"

    def __init__(self, *, fake_mode: str) -> None:
        self._fake_mode = fake_mode

    def run(self, request: ProviderRequest) -> ProviderResult:
        if request.stage == "detection" and self._fake_mode == "detection_success":
            return ProviderResult(
                outcome=ProviderOutcome.SUCCESS,
                provider_name=self.provider_name,
                model_id=self.model_id,
                payload={
                    "text_blocks": (
                        {
                            "provider_block_ref": "fake-block-1",
                            "bbox": {
                                "x": 10,
                                "y": 20,
                                "width": 80,
                                "height": 24,
                            },
                            "source_direction": "vertical",
                            "reading_order": 1,
                            "confidence": 0.93,
                        },
                        {
                            "provider_block_ref": "fake-block-2",
                            "bbox": {
                                "x": 12,
                                "y": 64,
                                "width": 84,
                                "height": 22,
                            },
                            "source_direction": "vertical",
                            "reading_order": 2,
                            "confidence": 0.91,
                        },
                    )
                },
            )

        if request.stage == "ocr" and self._fake_mode == "ocr_success":
            return ProviderResult(
                outcome=ProviderOutcome.SUCCESS,
                provider_name=self.provider_name,
                model_id=self.model_id,
                payload={
                    "ocr_items": tuple(
                        {
                            "text_block_id": text_block_id,
                            "source_text": f"fake_source_{index}",
                            "confidence": 0.96,
                            "detected_direction": "vertical",
                        }
                        for index, text_block_id in enumerate(
                            request.text_block_ids,
                            start=1,
                        )
                    )
                },
            )

        if request.stage == "translation" and self._fake_mode == "translation_success":
            return ProviderResult(
                outcome=ProviderOutcome.SUCCESS,
                provider_name=self.provider_name,
                model_id=self.model_id,
                payload={
                    "translations": tuple(
                        {
                            "text_block_id": text_block_id,
                            "translation_text": f"fake_translation_{index}",
                            "confidence": "high",
                            "needs_review": False,
                        }
                        for index, text_block_id in enumerate(
                            request.text_block_ids,
                            start=1,
                        )
                    )
                },
            )

        if request.stage == "translation" and self._fake_mode == "translation_failure":
            return ProviderResult(
                outcome=ProviderOutcome.FAILURE,
                provider_name=self.provider_name,
                model_id=self.model_id,
                error=ProviderError(
                    kind="provider_unavailable",
                    code="translation_provider_unavailable",
                    sanitized_message="translation provider is unavailable",
                ),
            )

        if (
            request.stage == "translation"
            and self._fake_mode == "translation_invalid_json"
        ):
            return ProviderResult(
                outcome=ProviderOutcome.INVALID_OUTPUT,
                provider_name=self.provider_name,
                model_id=self.model_id,
                error=ProviderError(
                    kind="invalid_output",
                    code="translation_invalid_json",
                    sanitized_message="translation provider returned invalid JSON",
                ),
            )

        if request.stage == "translation" and self._fake_mode == "translation_partial":
            first_text_block_id = request.text_block_ids[0]
            return ProviderResult(
                outcome=ProviderOutcome.PARTIAL_SUCCESS,
                provider_name=self.provider_name,
                model_id=self.model_id,
                payload={
                    "translations": (
                        {
                            "text_block_id": first_text_block_id,
                            "translation_text": "fake_translation_1",
                            "confidence": "medium",
                            "needs_review": False,
                        },
                    ),
                    "missing_targets": tuple(request.text_block_ids[1:]),
                },
                error=ProviderError(
                    kind="invalid_output",
                    code="translation_partial_output",
                    sanitized_message="translation output omitted one or more targets",
                ),
            )

        if request.stage == "translation" and self._fake_mode == "translation_refusal":
            return ProviderResult(
                outcome=ProviderOutcome.REFUSAL,
                provider_name=self.provider_name,
                model_id=self.model_id,
                error=ProviderError(
                    kind="provider_refusal",
                    code="translation_provider_refused",
                    sanitized_message="provider refused the translation request",
                    is_provider_refusal=True,
                ),
            )

        if request.stage == "cleaning" and self._fake_mode == "cleaning_skip":
            return ProviderResult(
                outcome=ProviderOutcome.PARTIAL_SUCCESS,
                provider_name=self.provider_name,
                model_id=self.model_id,
                payload={
                    "block_results": tuple(
                        {
                            "text_block_id": text_block_id,
                            "status_hint": "cannot_clean",
                            "reason_code": "cleaning_complex_background",
                        }
                        for text_block_id in request.text_block_ids
                    )
                },
                error=ProviderError(
                    kind="unsupported_content",
                    code="cleaning_complex_background",
                    sanitized_message="cleaner skipped a complex background region",
                ),
            )

        if request.stage == "cleaning" and self._fake_mode == "cleaning_success":
            temp_path = _write_temp_png(request, "cleaned.png")
            return ProviderResult(
                outcome=ProviderOutcome.SUCCESS,
                provider_name=self.provider_name,
                model_id=self.model_id,
                payload={"cleaned_image_temp_ref": "cleaned-image"},
                temp_files=(
                    ProviderTempFileRef(
                        temp_ref_id="cleaned-image",
                        kind="image",
                        temp_path=temp_path,
                        media_type="image/png",
                        expected_artifact_type="cleaned_image",
                        safety_flags={"may_contain_original_image": True},
                    ),
                ),
            )

        if request.stage == "typesetting" and self._fake_mode == "typesetting_overflow":
            temp_path = _write_temp_png(request, "typeset-preview.png")
            return ProviderResult(
                outcome=ProviderOutcome.PARTIAL_SUCCESS,
                provider_name=self.provider_name,
                model_id=self.model_id,
                payload={
                    "preview_temp_ref": "typeset-preview",
                    "layout_results": tuple(
                        {
                            "text_block_id": text_block_id,
                            "fitted": False,
                            "overflow": True,
                            "final_font_size": 10,
                            "line_count": 4,
                        }
                        for text_block_id in request.text_block_ids
                    ),
                },
                error=ProviderError(
                    kind="invalid_output",
                    code="typeset_overflow",
                    sanitized_message="typesetter produced overflow evidence",
                ),
                temp_files=(
                    ProviderTempFileRef(
                        temp_ref_id="typeset-preview",
                        kind="preview",
                        temp_path=temp_path,
                        media_type="image/png",
                        expected_artifact_type="typeset_preview_image",
                        safety_flags={
                            "may_contain_original_image": True,
                            "may_contain_translation": True,
                        },
                    ),
                ),
            )

        if request.stage == "typesetting" and self._fake_mode == "typesetting_success":
            temp_path = _write_temp_png(request, "typeset.png")
            return ProviderResult(
                outcome=ProviderOutcome.SUCCESS,
                provider_name=self.provider_name,
                model_id=self.model_id,
                payload={"typeset_image_temp_ref": "typeset-image"},
                temp_files=(
                    ProviderTempFileRef(
                        temp_ref_id="typeset-image",
                        kind="image",
                        temp_path=temp_path,
                        media_type="image/png",
                        expected_artifact_type="typeset_image",
                        safety_flags={
                            "may_contain_original_image": True,
                            "may_contain_translation": True,
                        },
                    ),
                ),
            )

        raise ValueError(
            f"Unsupported FakeProvider mode for stage: {self._fake_mode}/{request.stage}"
        )


def _write_temp_png(request: ProviderRequest, filename: str):
    request.attempt_temp_root.mkdir(parents=True, exist_ok=True)
    path = request.attempt_temp_root / filename
    path.write_bytes(_tiny_png(width=8, height=8))
    return path


def _tiny_png(*, width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    raw_rows = b"".join(b"\x00" + (b"\xff\x00\x00" * width) for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw_rows))
        + chunk(b"IEND", b"")
    )
