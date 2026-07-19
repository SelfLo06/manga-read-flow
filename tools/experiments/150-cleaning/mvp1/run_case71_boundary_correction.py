from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))

from manga_read_flow.application.clean_single_page import CleaningSliceInstanceInput, SinglePageCleaningCommand, SinglePageCleaningService
from manga_read_flow.application.import_page import ImportPageCommand, ImportPageService
from manga_read_flow.artifacts.service import ArtifactService
from manga_read_flow.persistence.project_store import AppStore
from manga_read_flow.providers.border_sampled_fill import BorderSampledFillCleanerProvider
from manga_read_flow.quality.cleaning_validation import validate_cleaning_output
from manga_read_flow.quality.text_aware_boundary import TextAwareBoundaryInputs, correct_text_aware_virtual_boundary

RUN = ROOT / "data/local/reviews/150-cleaning/single-page-correction-v0.1/case-71-g002-s02-run-v0.1"
SOURCE = ROOT / "data/local/reviews/150-cleaning/association-goal6-v0.1/full-page-v0.1/images/case-71.webp"
A = ROOT / "data/local/reviews/120-grouping/visual-contract-a-v0.1/run-v0.4/masks/case-71"
B = ROOT / "data/local/reviews/160-typesetting/visual-contract-b-v0.1/run-v0.7/artifacts/case-71"
D = ROOT / "data/local/reviews/150-cleaning/visual-contract-d-v0.1/run-v0.5/artifacts/case-71/579e153eb424310a"
OLD = ROOT / "data/local/reviews/150-cleaning/single-page-slice-v0.1/case-71-run-v0.3"
S1 = "case-71__g002__s01"; S2 = "case-71__g002__s02"
MASKS = {"case-71__g001__s01":"instance-e0c2b28d383d520e.png", S1:"instance-42de7cb555ad8d48.png", S2:"instance-f4a7e9962ed9bf09.png", "case-71__g003__s01":"instance-778d901a2f9bb11c.png", "case-71__g004__s01":"instance-deee9c658ef25719.png", "case-71__g005__s01":"instance-2d5e1ee679b751bc.png"}

def main() -> None:
    if RUN.exists(): raise SystemExit(f"refuse to overwrite existing run: {RUN}")
    (RUN / "masks").mkdir(parents=True); (RUN / "visuals").mkdir()
    rd = lambda p: cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) > 0
    s1, s2 = rd(A / MASKS[S1]), rd(A / MASKS[S2])
    root2 = B / "83e0a5ee5efce576"; required, protected, uncertainty = rd(root2 / "visible-support-candidate.png"), rd(root2 / "protected.png"), rd(root2 / "uncertainty.png")
    correction = correct_text_aware_virtual_boundary(TextAwareBoundaryInputs(s2, s1, uncertainty, protected, required, protected, uncertainty, source_sha256=_hash(SOURCE)), correction_ordinal=1)
    if correction.status != "COMPLETE": raise SystemExit(f"correction blocked: {correction.reason_code}")
    for name, mask in {"s01-instance-new":correction.neighbor_instance,"s02-instance-new":correction.primary_instance,"s02-safe-new":correction.primary_safe_edit,"s02-protected-new":correction.primary_protected,"s02-uncertainty-new":correction.uncertainty,"s02-virtual-new":correction.virtual_boundary,"s02-corridor":correction.corridor,"s02-guarded-required":correction.guarded_required}.items(): _mask(RUN / "masks" / f"{name}.png", mask)
    project = AppStore.initialize(RUN / "workspace").create_project(name="case-71 Slice F", source_language="ja", target_language="zh-Hans")
    repos = AppStore.initialize(RUN / "workspace").open_project(project.project_id).repositories()
    artifacts = ArtifactService(project_id=project.project_id, project_workspace_path=project.workspace_path, artifact_repository=repos.artifact_metadata)
    imported = ImportPageService(project_id=project.project_id, repositories=repos, artifact_service=artifacts).import_page(ImportPageCommand(source_path=SOURCE, batch_name="slice-f", page_index=1, batch_id="case-71-f", page_id="case-71"))
    for order, segment in enumerate(MASKS, 1): repos.content_state.create_text_block(text_block_id=segment, page_id="case-71", reading_order=order, ocr_status="done", translation_status="done")
    items=[]
    for order, segment in enumerate(MASKS, 1):
        instance = RUN / "masks/s01-instance-new.png" if segment == S1 else RUN / "masks/s02-instance-new.png" if segment == S2 else A / MASKS[segment]
        if segment == S1: px=(D / "required-support.png",D / "safe-edit.png",D / "protected.png",D / "uncertainty.png",True,"E1","COMPLETE","shared_boundary_revalidated")
        elif segment == S2: px=(root2 / "visible-support-candidate.png",RUN / "masks/s02-safe-new.png",RUN / "masks/s02-protected-new.png",RUN / "masks/s02-uncertainty-new.png",False,"E1","COMPLETE","text_aware_boundary_corrected")
        else: px=(None,None,None,None,False,"OUT_OF_SLICE","NOT_EVALUATED","no_frozen_pixel_cleaning_evidence")
        items.append(CleaningSliceInstanceInput(segment, f"{segment}::boundary-v1", _hash(instance), segment, f"{segment}::segment-v1", segment, order, instance, px[0],px[1],px[2],px[3],px[5],px[6],px[7], execute_cleaner=not px[4]))
    command=SinglePageCleaningCommand(page_id="case-71",batch_id="case-71-f",source_artifact_id=imported.original_artifact.artifact_id,source_image_path=SOURCE,visual_contract_revision_id="visual-contract::case-71::slice-f-v0.1",input_hash=_hash(RUN / "masks/s02-safe-new.png"),config_hash=sha256(b"border-sampled-fill-cleaner:mvp1-v0.1;text-aware-boundary-v0.1").hexdigest(),work_root=RUN / "work",instances=tuple(items),page_scope_complete=False)
    result=SinglePageCleaningService(project_id=project.project_id,repositories=repos,artifact_service=artifacts,cleaner_provider=BorderSampledFillCleanerProvider()).run(command)
    candidate=next((RUN / "workspace").rglob(f"*{result.candidate_artifact_id}*"))
    old=cv2.imread(str(OLD / "visuals/02-cleaning-candidate.png"),cv2.IMREAD_COLOR); src=cv2.imread(str(SOURCE),cv2.IMREAD_COLOR); s2out=cv2.imread(str(candidate),cv2.IMREAD_COLOR); changed=np.any(src != s2out,axis=2); combined=old.copy(); combined[changed]=s2out[changed]; cv2.imwrite(str(RUN / "visuals/combined-candidate.png"),combined)
    s1check=validate_cleaning_output(source_image_path=SOURCE,cleaned_image_path=OLD / "visuals/02-cleaning-candidate.png",required_support_path=D / "required-support.png",safe_edit_path=D / "safe-edit.png",instance_mask_path=RUN / "masks/s01-instance-new.png",protected_mask_path=D / "protected.png",uncertainty_mask_path=D / "uncertainty.png",output_dir=RUN / "s01-validator")
    _overlay(SOURCE, correction, changed, RUN / "visuals/correction-overlay.png")
    summary={"unsafe_before":int((required & ~rd(root2 / "safe-edit.png")).sum()),"unsafe_after":correction.unsafe_required_pixels,"fingerprint":correction.dependency_fingerprint,"decision":result.decision,"active_cleaned_artifact_id":result.active_cleaned_artifact_id,"s02_candidate_artifact_id":result.candidate_artifact_id,"s01_validation":s1check.metrics,"original_sha256":_hash(SOURCE),"changed_pixels_s02":int(changed.sum()),"instance_overlap":int((correction.primary_instance & correction.neighbor_instance).sum()),"correction_ordinal":1,"budget_after":0}
    (RUN / "summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (RUN / "FORM.md").write_text(_form(),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))

def _hash(path): return sha256(Path(path).read_bytes()).hexdigest()
def _mask(path, value): cv2.imwrite(str(path),(value.astype(np.uint8)*255))
def _overlay(source, correction, changed, output):
    image=cv2.imread(str(source),cv2.IMREAD_COLOR); image[correction.corridor]=[0,255,255]; image[correction.guarded_required]=[255,0,255]; image[changed]=[0,0,255]; cv2.imwrite(str(output),image)
def _form(): return """# Slice F case-71 g002/s02 人工 Gate\n\n![combined candidate](visuals/combined-candidate.png)\n\n![boundary / required / actual change](visuals/correction-overlay.png)\n\n- [ ] `PASS_TEXT_AWARE_BOUNDARY` / [ ] `FAIL` / [ ] `UNCLEAR`\n- [ ] `PASS_REQUIRED_COVERAGE` / [ ] `FAIL` / [ ] `UNCLEAR`\n- [ ] `PASS_LOCAL_CLEANING` / [ ] `FAIL` / [ ] `UNCLEAR`\n- [ ] `PASS_INSTANCE_ISOLATION` / [ ] `FAIL` / [ ] `UNCLEAR`\n- [ ] `ACCEPT_BOUNDED_CORRECTION` / [ ] `CHANGES_REQUIRED`\n\n本 Gate 仅评估 g002 contact cluster；其余四个 segment 仍为 OUT_OF_SLICE，active pointer 必须保持为空。\n"""
if __name__ == "__main__": main()
