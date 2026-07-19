from __future__ import annotations

import argparse
from pathlib import Path

import json

from .core import AuditConfig, regenerate_from_existing_outputs, run_audit, warm_cache


def main() -> int:
    parser = argparse.ArgumentParser(description="Local-only, non-semantic dataset audit")
    parser.add_argument("command", choices=("run", "warm-cache", "regenerate"))
    parser.add_argument("--input-root", type=Path, default=Path("data/local/datasets/manga-triplets"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/local/runs/150-cleaning/dataset-audit-v0.1"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/local/cache/150-cleaning/dataset-audit"))
    parser.add_argument("--analysis-long-edge", type=int, default=2048)
    parser.add_argument("--thumbnail-long-edge", type=int, default=512)
    parser.add_argument("--max-new-files", type=int, default=25, help="warm-cache only")
    parser.add_argument("--series-groups", type=Path, default=None, help="JSON work_id -> series_group_id; regenerate only")
    args = parser.parse_args()
    config = AuditConfig(input_root=args.input_root, output_dir=args.output_dir, cache_dir=args.cache_dir, analysis_long_edge=args.analysis_long_edge, thumbnail_long_edge=args.thumbnail_long_edge)
    if args.command == "warm-cache":
        print(warm_cache(config, args.max_new_files))
    elif args.command == "run":
        manifest = run_audit(config)
        print(f"completed {manifest['coverage']} run_id={manifest['run_id']}")
    else:
        groups = json.loads(args.series_groups.read_text(encoding="utf-8")) if args.series_groups else {}
        manifest = regenerate_from_existing_outputs(args.output_dir, groups)
        print(f"regenerated output hashes={len(manifest['output_sha256'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
