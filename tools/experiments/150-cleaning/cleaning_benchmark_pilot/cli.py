from __future__ import annotations

import argparse
from pathlib import Path

from .core import PilotConfig, run_pilot
from .workbook import (
    create_manual_review_workbook, create_region_review_workbook,
    validate_manual_review_workbook, validate_region_review_workbook,
    write_back_manual_review_workbook, write_back_region_review_workbook,
)
from .region_candidate_pilot import create_region_candidate_pilot_workbook, run_region_candidate_pilot
from .hard_case_supplement import run_hard_case_supplement
from .hard_case_supplement_v2 import run_hard_case_supplement_v2


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare and review local-only Cleaning Benchmark Pilot materials")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--input-root", type=Path, default=Path("data/local/datasets/manga-triplets"))
    prepare.add_argument("--audit-dir", type=Path, default=Path("data/local/runs/150-cleaning/dataset-audit-v0.1"))
    prepare.add_argument("--output-dir", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1"))
    prepare.add_argument("--review-dir", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/artifacts"))
    prepare.add_argument("--selection-seed", type=int, default=20260714)
    prepare.add_argument("--page-target", type=int, default=24)
    prepare.add_argument("--regions-per-page", type=int, default=2)
    workbook = subparsers.add_parser("create-workbook")
    workbook.add_argument("--csv", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/manual-review-resolution.csv"))
    workbook.add_argument("--workbook", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/manual-review-workbook.xlsx"))
    workbook.add_argument("--review-dir", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/artifacts"))
    writeback = subparsers.add_parser("writeback-workbook")
    writeback.add_argument("--csv", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/manual-review-resolution.csv"))
    writeback.add_argument("--workbook", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/manual-review-workbook.xlsx"))
    writeback.add_argument("--input-root", type=Path, default=Path("data/local/datasets/manga-triplets"))
    region_workbook = subparsers.add_parser("create-region-workbook")
    region_workbook.add_argument("--region-csv", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/region-review.csv"))
    region_workbook.add_argument("--workbook", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/region-review-workbook.xlsx"))
    region_workbook.add_argument("--review-dir", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/artifacts"))
    region_workbook.add_argument("--selection-csv", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/page-selection.csv"))
    region_workbook.add_argument("--manual-resolution-csv", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/manual-review-resolution.csv"))
    region_writeback = subparsers.add_parser("writeback-region-workbook")
    region_writeback.add_argument("--region-csv", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/region-review.csv"))
    region_writeback.add_argument("--workbook", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/region-review-workbook.xlsx"))
    region_writeback.add_argument("--manual-resolution-csv", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/manual-review-resolution.csv"))
    candidate_pilot = subparsers.add_parser("run-region-candidate-pilot")
    candidate_pilot.add_argument("--input-root", type=Path, default=Path("data/local/datasets/manga-triplets"))
    candidate_pilot.add_argument("--selection-csv", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/page-selection.csv"))
    candidate_pilot.add_argument("--triplet-csv", type=Path, default=Path("data/local/runs/150-cleaning/dataset-audit-v0.1/triplet-quality.csv"))
    candidate_pilot.add_argument("--output-csv", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/region-candidate-pilot.csv"))
    candidate_pilot.add_argument("--review-dir", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/artifacts"))
    candidate_pilot.add_argument("--workbook", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/region-candidate-pilot-workbook.xlsx"))
    supplement=subparsers.add_parser("run-hard-case-supplement"); supplement.add_argument("--input-root",type=Path,default=Path("data/local/datasets/manga-triplets")); supplement.add_argument("--selection-csv",type=Path,default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/page-selection.csv")); supplement.add_argument("--triplet-csv",type=Path,default=Path("data/local/runs/150-cleaning/dataset-audit-v0.1/triplet-quality.csv")); supplement.add_argument("--output-csv",type=Path,default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/region-candidate-hard-case-supplement.csv")); supplement.add_argument("--review-dir",type=Path,default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/artifacts"))
    supplement_v2 = subparsers.add_parser("run-hard-case-supplement-v2")
    supplement_v2.add_argument("--input-root", type=Path, default=Path("data/local/datasets/manga-triplets"))
    supplement_v2.add_argument("--selection-csv", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/page-selection.csv"))
    supplement_v2.add_argument("--triplet-csv", type=Path, default=Path("data/local/runs/150-cleaning/dataset-audit-v0.1/triplet-quality.csv"))
    supplement_v2.add_argument("--pilot-csv", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/region-candidate-pilot.csv"))
    supplement_v2.add_argument("--v1-csv", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/region-candidate-hard-case-supplement.csv"))
    supplement_v2.add_argument("--output-dir", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1"))
    supplement_v2.add_argument("--review-dir", type=Path, default=Path("data/local/reviews/150-cleaning/benchmark-pilot-v0.1/artifacts"))
    args = parser.parse_args()
    if args.command == "prepare":
        result = run_pilot(PilotConfig(**{key: value for key, value in vars(args).items() if key != "command"}))
        print(result)
    elif args.command == "create-workbook":
        create_manual_review_workbook(args.csv, args.workbook, args.review_dir)
        print(args.workbook)
    elif args.command == "writeback-workbook":
        _, summary = validate_manual_review_workbook(args.workbook, args.csv, args.input_root)
        write_back_manual_review_workbook(args.workbook, args.csv, args.input_root)
        print({"csv": str(args.csv), "validation": summary})
    elif args.command == "create-region-workbook":
        print(create_region_review_workbook(args.region_csv, args.workbook, args.review_dir, args.selection_csv, args.manual_resolution_csv))
    elif args.command == "run-region-candidate-pilot":
        print(run_region_candidate_pilot(args.input_root, args.selection_csv, args.triplet_csv, args.output_csv, args.review_dir))
        create_region_candidate_pilot_workbook(args.output_csv, args.workbook, args.review_dir)
        print(args.workbook)
    elif args.command == "run-hard-case-supplement": print(run_hard_case_supplement(args.input_root,args.selection_csv,args.triplet_csv,args.output_csv,args.review_dir))
    elif args.command == "run-hard-case-supplement-v2": print(run_hard_case_supplement_v2(args.input_root, args.selection_csv, args.triplet_csv, args.pilot_csv, args.v1_csv, args.output_dir, args.review_dir))
    else:
        _, summary = validate_region_review_workbook(args.workbook, args.region_csv, args.manual_resolution_csv)
        write_back_region_review_workbook(args.workbook, args.region_csv, args.manual_resolution_csv)
        print({"csv": str(args.region_csv), "validation": summary})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
