from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from manga_read_flow.domain.provider_contracts import (
    ProviderIdentity,
    ProviderOutcome,
    ProviderRequest,
    ProviderResult,
    ProviderTempFileRef,
)


class BorderSampledFillCleanerProvider:
    """Bounded E1 cleaner; all durable promotion is owned by ArtifactService."""

    identity = ProviderIdentity(
        provider_name="border-sampled-fill-cleaner",
        provider_kind="cleaner",
        model_id=None,
        tool_name="border_sampled_fill",
        tool_version="mvp1-v0.1",
    )

    def run(self, request: ProviderRequest) -> ProviderResult:
        if request.stage != "cleaning":
            raise ValueError("BorderSampledFillCleanerProvider only supports cleaning.")
        source = _read_rgb(Path(str(request.inputs["source_image_path"])))
        candidate = _read_mask(Path(str(request.inputs["candidate_mask_path"])))
        safe_edit = _read_mask(Path(str(request.inputs["safe_edit_mask_path"])))
        instance = _read_mask(Path(str(request.inputs["instance_mask_path"])))
        protected = _read_mask(Path(str(request.inputs["protected_mask_path"])))
        uncertainty = _read_mask(Path(str(request.inputs["uncertainty_mask_path"])))
        if not (source.shape[:2] == candidate.shape == safe_edit.shape == instance.shape == protected.shape == uncertainty.shape):
            raise ValueError("Cleaner inputs must share image dimensions.")
        writable = candidate & safe_edit & instance & ~protected & ~uncertainty
        ring = _dilate(writable, 4) & instance & ~_dilate(writable, 1) & ~protected & ~uncertainty
        if int(ring.sum()) < 16:
            return ProviderResult(
                outcome=ProviderOutcome.PARTIAL_SUCCESS,
                provider_name=self.identity.provider_name,
                payload={"block_results": [{"status_hint": "cannot_clean", "reason_code": "insufficient_local_background"}]},
            )
        fill = np.median(source[ring], axis=0).astype(np.uint8)
        output = source.copy()
        output[writable] = fill
        changed = np.any(output != source, axis=2)
        out_path = request.attempt_temp_root / "cleaned.png"
        changed_path = request.attempt_temp_root / "actual-changed.png"
        evidence_path = request.attempt_temp_root / "cleaner-evidence.json"
        _write_rgb(out_path, output)
        cv2.imwrite(str(changed_path), (changed.astype(np.uint8) * 255))
        evidence_path.write_text(json.dumps({"candidate_pixels": int(writable.sum()), "actual_changed_pixels": int(changed.sum()), "fill_rgb": fill.tolist()}, sort_keys=True), encoding="utf-8")
        return ProviderResult(
            outcome=ProviderOutcome.SUCCESS,
            provider_name=self.identity.provider_name,
            payload={"block_results": [{"status_hint": "cleaned", "reason_code": "bounded_e1"}]},
            temp_files=(
                ProviderTempFileRef("cleaned_image", "image", out_path, "image/png", "cleaned_image"),
                ProviderTempFileRef("actual_changed", "mask", changed_path, "image/png", "mask_image"),
                ProviderTempFileRef("cleaner_evidence", "json", evidence_path, "application/json", "validation_evidence"),
            ),
        )


def _read_rgb(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Unreadable cleaner image: {path}")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def _read_mask(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"Unreadable cleaner mask: {path}")
    return image > 0


def _write_rgb(path: Path, image: np.ndarray) -> None:
    if not cv2.imwrite(str(path), cv2.cvtColor(image, cv2.COLOR_RGB2BGR)):
        raise ValueError("Unable to write cleaner output.")


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    return cv2.dilate(mask.astype(np.uint8), np.ones((radius * 2 + 1, radius * 2 + 1), np.uint8)) > 0
