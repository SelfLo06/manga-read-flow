from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from manga_read_flow.application.clean_single_page import (  # noqa: E402
    CleaningSliceInstanceInput,
    SinglePageCleaningCommand,
    SinglePageCleaningService,
)
from manga_read_flow.application.import_page import ImportPageCommand, ImportPageService  # noqa: E402
from manga_read_flow.artifacts.service import ArtifactService  # noqa: E402
from manga_read_flow.persistence.project_store import AppStore  # noqa: E402
from manga_read_flow.providers.border_sampled_fill import BorderSampledFillCleanerProvider  # noqa: E402


RUN_ROOT = ROOT / "data/local/mvp1-single-page-cleaning-slice-v0.1/case-71-run-v0.3"
SOURCE = ROOT / "data/local/text-seeded-container-association/goal6-minimal-cleaning-v0.1/full-page-v0.1/images/case-71.webp"
A_ROOT = ROOT / "data/local/mvp1-visual-contract-spike-a-v0.1/run-v0.4"
B_ROOT = ROOT / "data/local/mvp1-visual-contract-spike-b-v0.1/run-v0.7/artifacts/case-71"
D_ROOT = ROOT / "data/local/mvp1-visual-contract-spike-d-v0.1/run-v0.5/artifacts/case-71/579e153eb424310a"


INSTANCE_MASKS = {
    "case-71__g001__s01": "instance-e0c2b28d383d520e.png",
    "case-71__g002__s01": "instance-42de7cb555ad8d48.png",
    "case-71__g002__s02": "instance-f4a7e9962ed9bf09.png",
    "case-71__g003__s01": "instance-778d901a2f9bb11c.png",
    "case-71__g004__s01": "instance-deee9c658ef25719.png",
    "case-71__g005__s01": "instance-2d5e1ee679b751bc.png",
}


def main() -> None:
    if RUN_ROOT.exists():
        raise SystemExit(f"Run directory already exists; choose a new run id: {RUN_ROOT}")
    RUN_ROOT.mkdir(parents=True)
    visuals = RUN_ROOT / "visuals"
    visuals.mkdir()

    snapshot = json.loads((A_ROOT / "visual-contract-snapshot.json").read_text(encoding="utf-8"))
    page_snapshot = next(page for page in snapshot["pages"] if page["page_id"] == "case-71")
    segments = {segment["segment_id"]: segment for segment in page_snapshot["text_segments"]}
    instances = {
        instance["segment_ids"][0]: instance
        for instance in page_snapshot["bubble_instances"]
    }

    store = AppStore.initialize(RUN_ROOT / "workspace")
    project = store.create_project(
        name="MVP-1 case-71 Cleaning slice",
        source_language="ja",
        target_language="zh-Hans",
    )
    opened = store.open_project(project.project_id)
    repositories = opened.repositories()
    artifact_service = ArtifactService(
        project_id=project.project_id,
        project_workspace_path=project.workspace_path,
        artifact_repository=repositories.artifact_metadata,
    )
    imported = ImportPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
    ).import_page(
        ImportPageCommand(
            source_path=SOURCE,
            batch_name="case-71 formal slice",
            page_index=1,
            batch_id="batch-case-71",
            page_id="case-71",
            original_filename="case-71.webp",
        )
    )
    for segment in page_snapshot["text_segments"]:
        repositories.content_state.create_text_block(
            text_block_id=segment["segment_id"],
            page_id="case-71",
            reading_order=segment["reading_order"],
            ocr_status="done",
            translation_status="done",
        )

    slice_inputs = tuple(
        _instance_input(segment_id, segments[segment_id], instances[segment_id])
        for segment_id in INSTANCE_MASKS
    )
    input_payload = {
        "source_sha256": _sha256(SOURCE),
        "instances": [
            {
                "segment_id": item.text_segment_id,
                "instance_revision_id": item.bubble_instance_revision_id,
                "region_hash": item.region_hash,
                "instance_mask_sha256": _sha256(item.instance_mask_path),
                "required_sha256": _optional_sha256(item.required_support_path),
                "safe_sha256": _optional_sha256(item.safe_edit_path),
                "protected_sha256": _optional_sha256(item.protected_mask_path),
                "uncertainty_sha256": _optional_sha256(item.uncertainty_mask_path),
                "eligibility": item.eligibility,
                "required_safe_completeness": item.required_safe_completeness,
                "reason_code": item.reason_code,
            }
            for item in slice_inputs
        ],
    }
    input_hash = sha256(_canonical_json(input_payload)).hexdigest()
    config_hash = sha256(b"border-sampled-fill-cleaner:mvp1-v0.1").hexdigest()
    original_artifact_path = project.workspace_path / imported.original_artifact.relative_path
    original_before_hash = _sha256(original_artifact_path)
    result = SinglePageCleaningService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
        cleaner_provider=BorderSampledFillCleanerProvider(),
    ).run(
        SinglePageCleaningCommand(
            page_id="case-71",
            batch_id="batch-case-71",
            source_artifact_id=imported.original_artifact.artifact_id,
            source_image_path=original_artifact_path,
            visual_contract_revision_id="visual-contract::case-71::formal-v0.1",
            input_hash=input_hash,
            config_hash=config_hash,
            work_root=RUN_ROOT / "work",
            instances=slice_inputs,
        )
    )
    candidate = repositories.artifact_metadata.get_artifact(result.candidate_artifact_id)
    candidate_path = project.workspace_path / candidate.relative_path
    original_after_hash = _sha256(original_artifact_path)

    original_visual = visuals / "01-original.png"
    candidate_visual = visuals / "02-cleaning-candidate.png"
    applied_visual = visuals / "03-actual-applied-overlay.png"
    blocking_visual = visuals / "04-blocking-instance-overlay.png"
    _write_png(original_visual, _read_rgb(original_artifact_path))
    _write_png(candidate_visual, _read_rgb(candidate_path))
    _actual_applied_overlay(original_artifact_path, candidate_path, applied_visual)
    _blocking_overlay(
        source_path=original_artifact_path,
        instance_path=A_ROOT / "masks/case-71/instance-f4a7e9962ed9bf09.png",
        required_path=B_ROOT / "83e0a5ee5efce576/visible-support-candidate.png",
        safe_path=B_ROOT / "83e0a5ee5efce576/safe-edit.png",
        output_path=blocking_visual,
    )

    summary = {
        "schema_version": "mvp1-single-page-cleaning-slice-v1",
        "page_id": "case-71",
        "decision": "BLOCKED_REVIEW" if result.decision == "block" else "PASS",
        "provider_called": result.provider_called,
        "candidate_artifact_id": result.candidate_artifact_id,
        "evidence_artifact_id": result.evidence_artifact_id,
        "active_cleaned_artifact_id": result.active_cleaned_artifact_id,
        "issue_ids": list(result.issue_ids),
        "input_hash": input_hash,
        "config_hash": config_hash,
        "original_hash_before": original_before_hash,
        "original_hash_after": original_after_hash,
        "original_unchanged": original_before_hash == original_after_hash,
        "timings_ms": result.timings_ms,
        "dispositions": input_payload["instances"],
    }
    (RUN_ROOT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (RUN_ROOT / "FORM.md").write_text(_form(summary), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _instance_input(segment_id: str, segment: dict, instance: dict) -> CleaningSliceInstanceInput:
    instance_path = A_ROOT / "masks/case-71" / INSTANCE_MASKS[segment_id]
    if segment_id == "case-71__g002__s01":
        pixel_paths = {
            "required": D_ROOT / "required-support.png",
            "safe": D_ROOT / "safe-edit.png",
            "protected": D_ROOT / "protected.png",
            "uncertainty": D_ROOT / "uncertainty.png",
        }
        eligibility, completeness, reason = "E1", "COMPLETE", "spike_d_pass"
    elif segment_id == "case-71__g002__s02":
        root = B_ROOT / "83e0a5ee5efce576"
        pixel_paths = {
            "required": root / "visible-support-candidate.png",
            "safe": root / "safe-edit.png",
            "protected": root / "protected.png",
            "uncertainty": root / "uncertainty.png",
        }
        eligibility = "E1"
        completeness = "INCOMPLETE_REVIEW"
        reason = "required_text_not_safely_editable"
    else:
        pixel_paths = {"required": None, "safe": None, "protected": None, "uncertainty": None}
        eligibility = "OUT_OF_SLICE"
        completeness = "NOT_EVALUATED"
        reason = "no_frozen_pixel_cleaning_evidence"
    revision_suffix = sha256(segment_id.encode("utf-8")).hexdigest()[:20]
    return CleaningSliceInstanceInput(
        bubble_instance_id=instance["instance_id"],
        bubble_instance_revision_id=instance["revision_id"],
        region_hash=instance["mask_sha256"],
        text_segment_id=segment_id,
        text_segment_revision_id=f"text-segment-revision::{revision_suffix}",
        source_text_block_id=segment_id,
        segment_order=segment["reading_order"],
        instance_mask_path=instance_path,
        required_support_path=pixel_paths["required"],
        safe_edit_path=pixel_paths["safe"],
        protected_mask_path=pixel_paths["protected"],
        uncertainty_mask_path=pixel_paths["uncertainty"],
        eligibility=eligibility,
        required_safe_completeness=completeness,
        reason_code=reason,
    )


def _actual_applied_overlay(source_path: Path, candidate_path: Path, output_path: Path) -> None:
    source = _read_rgb(source_path)
    candidate = _read_rgb(candidate_path)
    changed = np.any(source != candidate, axis=2)
    overlay = source.copy()
    overlay[changed] = ((overlay[changed].astype(np.uint16) + np.array([255, 0, 0])) // 2).astype(np.uint8)
    _label(overlay, "RED = ACTUAL APPLIED PIXELS (g002/s01 only)")
    _write_png(output_path, overlay)


def _blocking_overlay(*, source_path: Path, instance_path: Path, required_path: Path, safe_path: Path, output_path: Path) -> None:
    source = _read_rgb(source_path)
    instance = _read_mask(instance_path)
    required = _read_mask(required_path)
    safe = _read_mask(safe_path)
    unsafe = required & ~safe
    overlay = source.copy()
    overlay[safe] = ((overlay[safe].astype(np.uint16) + np.array([0, 255, 0])) // 2).astype(np.uint8)
    overlay[required] = ((overlay[required].astype(np.uint16) + np.array([255, 0, 255])) // 2).astype(np.uint8)
    overlay[unsafe] = np.array([255, 0, 0], dtype=np.uint8)
    boundary = instance & ~(cv2.erode(instance.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
    overlay[boundary] = np.array([0, 255, 255], dtype=np.uint8)
    _label(overlay, "g002/s02 BLOCK: CYAN instance | GREEN safe | MAGENTA required | RED unsafe")
    _write_png(output_path, overlay)


def _form(summary: dict) -> str:
    timings = summary["timings_ms"]
    return f"""# case-71 正式单页 Cleaning 切片人工审查 FORM

本表审查的是正式 Workflow/Artifact/Repository 路径，不是整页 Cleaning 完成图。自动裁决为 `BLOCKED_REVIEW`：`g002/s01` 已生成候选，`g002/s02` 因 6 个 required support 像素不安全而阻塞，`active_cleaned_artifact_id` 保持为空。

## 1. 原图

![case-71 原图](visuals/01-original.png)

## 2. 正式候选图

只有 `g002/s01` 获准写入候选；其他文字保留是本切片范围与门禁的预期结果。

![case-71 Cleaning candidate](visuals/02-cleaning-candidate.png)

- [ ] `PASS_LOCAL_CLEANING`：获准区域无可辨残字、无明显白块或边界损伤
- [ ] `FAIL_LOCAL_CLEANING`：获准区域仍有残字或视觉损伤
- [ ] `UNCLEAR`

## 3. 实际写回像素

红色只表示从原图与候选重新计算得到的 ActualChangedPixelMask，不使用 Provider 自报计数。

![actual applied overlay](visuals/03-actual-applied-overlay.png)

- [ ] `PASS_APPLY_SCOPE`：实际写回只属于 `g002/s01`
- [ ] `FAIL_APPLY_SCOPE`：存在跨实例或无关区域写回
- [ ] `UNCLEAR`

## 4. 阻塞实例 `g002/s02`

青色为独立 BubbleInstance 边界，绿色为 safe edit，紫色为 required support，红色为 required 但不安全的像素。

![blocking instance overlay](visuals/04-blocking-instance-overlay.png)

- [ ] `PASS_BLOCK_REASON`：该实例保持不写回且阻塞原因表达清楚
- [ ] `FAIL_BLOCK_REASON`：实例/证据绑定错误或阻塞理由不成立
- [ ] `UNCLEAR`

## 5. 正式路径裁决

- [ ] `ACCEPT_BLOCKED_REVIEW`：候选可审计、原图未变、active pointer 未更新，门禁行为正确
- [ ] `CHANGES_REQUIRED`

备注：

```text

```

## 自动事实（无需填写）

```text
decision = {summary['decision']}
active_cleaned_artifact_id = {summary['active_cleaned_artifact_id']}
original_unchanged = {str(summary['original_unchanged']).lower()}
provider_called = {str(summary['provider_called']).lower()}
contract/persistence = {timings.get('contract_artifact_and_persistence', 0):.3f} ms
provider/promotion = {timings.get('provider_and_output_promotion', 0):.3f} ms
validator/evidence = {timings.get('validator_and_evidence_promotion', 0):.3f} ms
quality = {timings.get('quality_classification', 0):.3f} ms
decision transaction = {timings.get('decision_transaction', 0):.3f} ms
total = {timings.get('total', 0):.3f} ms
```
"""


def _read_rgb(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Unreadable image: {path}")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def _read_mask(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"Unreadable mask: {path}")
    return image > 0


def _write_png(path: Path, image: np.ndarray) -> None:
    if not cv2.imwrite(str(path), cv2.cvtColor(image, cv2.COLOR_RGB2BGR)):
        raise ValueError(f"Unable to write image: {path}")


def _label(image: np.ndarray, text: str) -> None:
    cv2.rectangle(image, (0, 0), (image.shape[1], 42), (0, 0, 0), -1)
    cv2.putText(image, text, (12, 29), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2, cv2.LINE_AA)


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _optional_sha256(path: Path | None) -> str | None:
    return _sha256(path) if path is not None else None


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


if __name__ == "__main__":
    main()
