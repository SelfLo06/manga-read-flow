from __future__ import annotations
import csv, hashlib, json, shutil
from collections import Counter
from pathlib import Path
import cv2, numpy as np
from .core import _load_rgb, _relative, _warp_textless, sha256_file
from .region_candidate_pilot import _crop, _preview, _read_csv, extract_container_candidates, ANNOTATION_VERSION

FIELDS=("candidate_id","work_id","page_triplet_id","selection_bucket","selection_reason","text_area_ratio","boundary_distance","background_complexity_proxy","protected_overlap_ratio","candidate_generation_confidence","expected_disposition","jp_source_path","textless_source_path","zh_source_path","crop_bbox_xywh","candidate_mask_path","preview_path")
BUCKETS=("boundary-sensitive","transparent-or-textured","irregular-container","small-or-fragmented-text","negative-or-abstention")
QUOTAS={"boundary-sensitive":3,"transparent-or-textured":4,"irregular-container":2,"small-or-fragmented-text":2,"negative-or-abstention":2}

def _write(path, rows):
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)

def run_hard_case_supplement(input_root:Path, selection_csv:Path, triplet_csv:Path, output_csv:Path, review_root:Path)->dict:
    pages=_read_csv(selection_csv); trips=_read_csv(triplet_csv); transforms={hashlib.sha256(x['original_path'].encode()).hexdigest()[:16]:x['textless_transform_matrix'] for x in trips}
    pool=[]
    for page in pages:
        jp,tl=_load_rgb(input_root/page['jp_source_path']),_load_rgb(input_root/page['textless_source_path']); transform=transforms[page['page_triplet_id']]
        diff,protected,candidates,uncertain=extract_container_candidates(jp,tl,transform)
        for index,c in enumerate(candidates):
            x,y,w,h=c['container']; area=max(1,w*h); text=float(np.count_nonzero(c['mask'][y:y+h,x:x+w]))/area
            edge=float(np.mean(cv2.Canny(cv2.cvtColor(jp[y:y+h,x:x+w],cv2.COLOR_RGB2GRAY),60,150)>0)); complexity=round(edge+float(np.std(jp[y:y+h,x:x+w]))/255,6)
            bd=min(x,y,jp.shape[1]-(x+w),jp.shape[0]-(y+h)); aspect=w/max(1,h)
            tags=[]
            if c['unit_type']=='text_container' and text>.08: tags.append('boundary-sensitive')
            if complexity>.25:tags.append('transparent-or-textured')
            if aspect>2.0 or aspect<.5:tags.append('irregular-container')
            if text<.13 or c['unit_type']=='text_instance_cluster':tags.append('small-or-fragmented-text')
            pool.append((tags,False,page,jp,tl,transform,diff,protected,c, text,bd,complexity))
        for c in uncertain[:20]:pool.append((['negative-or-abstention'],True,page,jp,tl,transform,diff,protected,c,0.,0,0.))
    selected=[];used=set(); pool_counts=Counter(tag for tags,*_ in pool for tag in tags)
    for bucket in BUCKETS:
        for item in sorted((x for x in pool if bucket in x[0]),key=lambda x:(x[1],x[2]['page_triplet_id'],str(x[8]))) :
            key=(item[2]['page_triplet_id'],str(item[8]));
            if key in used:continue
            selected.append((bucket,item));used.add(key)
            if sum(1 for b,_ in selected if b==bucket)>=QUOTAS[bucket]:break
    if any(sum(1 for b,_ in selected if b==bucket)<quota for bucket,quota in QUOTAS.items()):raise RuntimeError(f'hard_case_bucket_quota_unmet:{dict(pool_counts)}')
    root=review_root/'hard-case-supplement';shutil.rmtree(root,ignore_errors=True);rows=[]
    for number,(bucket,item) in enumerate(selected,1):
        tags,negative,page,jp,tl,transform,diff,protected,c,text,bd,complexity=item; cid=f'hard-{number:02d}'
        if negative:
            crop=_crop(c['component'][:4],jp.shape[:2]);mask=np.zeros(diff.shape,np.uint8);x,y,w,h,_=c['component'];mask[y:y+h,x:x+w]=diff[y:y+h,x:x+w];reason='unreliable_grouping_or_non_bubble_text';disp='REVIEW_REQUIRED / SKIP'
        else:
            crop=_crop(c['container'],jp.shape[:2]);mask=c['mask'];reason=f'{bucket}; tags={"|".join(tags)}';disp='REVIEW_REQUIRED'
        mp=root/'masks'/f'{cid}.png';pp=root/'previews'/f'{cid}.png';mp.parent.mkdir(parents=True,exist_ok=True);cv2.imwrite(str(mp),mask);_preview(jp,_warp_textless(tl,jp.shape[:2],transform),diff,mask,protected,crop,pp)
        rows.append({'candidate_id':cid,'work_id':page['work_id'],'page_triplet_id':page['page_triplet_id'],'selection_bucket':bucket,'selection_reason':reason,'text_area_ratio':f'{text:.6f}','boundary_distance':str(bd),'background_complexity_proxy':str(complexity),'protected_overlap_ratio':f'{float(np.mean(protected[mask>0]>0)) if np.any(mask) else 0:.6f}','candidate_generation_confidence':'low' if negative else 'medium','expected_disposition':disp,'jp_source_path':page['jp_source_path'],'textless_source_path':page['textless_source_path'],'zh_source_path':page['zh_source_path'],'crop_bbox_xywh':json.dumps(crop),'candidate_mask_path':_relative(mp,review_root),'preview_path':_relative(pp,review_root)})
    _write(output_csv,rows);return {'pool':dict(pool_counts),'selected':dict(Counter(r['selection_bucket'] for r in rows)),'count':len(rows)}
