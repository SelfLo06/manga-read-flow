from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

from tools.experiments.grouping_120.text_seeded_container_association import goal7_phase_b as phase_b


MAX_PARALLEL_WORKERS = 3


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_phase_c_selection(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for page in matrix["pages"]:
        for cluster in page["clusters"]:
            if cluster["route"] != "LOCAL_B1_CANDIDATE":
                continue
            items.append(
                {
                    "review_id": f"P3-{len(items) + 1:03d}",
                    "category": "frozen_local_candidate",
                    "execute_b1": True,
                    "human_labels": {},
                    "cluster": cluster,
                }
            )
    return items


def freeze_phase_c_config(matrix_path: Path, phase_b_review_path: Path, s1_results_path: Path, output_path: Path) -> Path:
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite Phase C config: {output_path}")
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    phase_b_review = json.loads(phase_b_review_path.read_text(encoding="utf-8"))
    s1 = json.loads(s1_results_path.read_text(encoding="utf-8"))
    if phase_b_review.get("verdict") != "PASS_TO_PHASE_C":
        raise RuntimeError("Phase B does not authorize Phase C")
    if s1.get("status") != "completed" or not s1.get("input_hashes_unchanged"):
        raise RuntimeError("S1 is not frozen and unchanged")
    items = build_phase_c_selection(matrix)
    payload = {
        "schema_version": "goal7-phase-c-config-v1",
        "status": "FROZEN",
        "source_hashes": {
            "phase_a_matrix": _sha256(matrix_path),
            "phase_b_human_review": _sha256(phase_b_review_path),
            "s1_results": _sha256(s1_results_path),
        },
        "parameters": {
            "route_filter": "LOCAL_B1_CANDIDATE",
            "max_roi_pixels": phase_b.MAX_ROI_PIXELS,
            "max_queue_entries": phase_b.MAX_QUEUE_ENTRIES,
            "max_working_memory_mb": phase_b.MAX_WORKING_MEMORY_MB,
            "max_algorithm_seconds": phase_b.MAX_ALGORITHM_SECONDS,
            "parallel_workers": MAX_PARALLEL_WORKERS,
            "cleaning": False,
            "pixel_text_mask": False,
            "auto_accept": False,
        },
        "route_summary": matrix["summary"],
        "candidate_count": len(items),
        "items": items,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def _run_one(request_path: Path, case_dir: Path, cwd: Path) -> tuple[int, float, float, str, str]:
    command = [
        sys.executable,
        "-m",
        "tools.experiments.grouping_120.text_seeded_container_association.goal7_phase_b",
        "worker",
        "--request",
        str(request_path),
        "--output-dir",
        str(case_dir),
    ]
    return phase_b._monitor_worker(command, cwd)


def _build_sample_contact_sheet(results: list[dict[str, Any]], output_dir: Path) -> None:
    by_page: dict[str, dict[str, Any]] = {}
    for result in results:
        if result.get("status") == "B1_COMPLETED":
            by_page.setdefault(result["page_id"], result)
    pages = sorted(by_page)
    if not pages:
        return
    positions = sorted({round(index * (len(pages) - 1) / 11) for index in range(min(12, len(pages)))})
    sample = [by_page[pages[position]] for position in positions]
    phase_b._write_contact_sheet(sample, output_dir)
    (output_dir / "CONTACT-SHEET.png").rename(output_dir / "SAMPLE-CONTACT-SHEET.png")


def run_phase_c(config_path: Path, s1_results_path: Path, root: Path, output_dir: Path) -> Path:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite Phase C output: {output_dir}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    s1 = json.loads(s1_results_path.read_text(encoding="utf-8"))
    if config.get("status") != "FROZEN":
        raise RuntimeError("Phase C config is not frozen")
    assets = {asset["asset_id"]: asset for asset in s1["assets"]}
    output_dir.mkdir(parents=True)
    requests_dir = output_dir / "requests"
    cases_dir = output_dir / "cases"
    requests_dir.mkdir()
    cases_dir.mkdir()
    cwd = Path(__file__).resolve().parents[3]
    jobs: list[tuple[dict[str, Any], Path, Path]] = []

    for item in config["items"]:
        cluster = item["cluster"]
        asset = assets[cluster["page_id"]]
        source = root / asset["relative_path"]
        if _sha256(source) != asset["sha256"]:
            raise RuntimeError(f"Frozen source changed: {cluster['page_id']}")
        request = phase_b._prepare_request(item, asset, source)
        request_path = requests_dir / f'{item["review_id"]}.json'
        request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        jobs.append((item, request_path, cases_dir / item["review_id"]))

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
        submitted = {
            executor.submit(_run_one, request_path, case_dir, cwd): (item, case_dir)
            for item, request_path, case_dir in jobs
        }
        for future in concurrent.futures.as_completed(submitted):
            item, case_dir = submitted[future]
            returncode, wall_seconds, peak_rss_mb, stdout, stderr = future.result()
            if returncode != 0:
                results.append(
                    {
                        "review_id": item["review_id"],
                        "page_id": item["cluster"]["page_id"],
                        "cluster_id": item["cluster"]["cluster_id"],
                        "status": "WORKER_TIMEOUT" if returncode == 124 else "WORKER_CRASH",
                        "returncode": returncode,
                        "wall_seconds": wall_seconds,
                        "peak_rss_mb": peak_rss_mb,
                        "stdout": stdout[-2000:],
                        "stderr": stderr[-2000:],
                    }
                )
                continue
            result_path = case_dir / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result.update(
                {
                    "wall_seconds": wall_seconds,
                    "peak_rss_mb": peak_rss_mb,
                    "worker_returncode": returncode,
                    "recommended_decision": "REVIEW_REQUIRED",
                    "auto_accept": False,
                }
            )
            if result["algorithm_seconds"] >= phase_b.MAX_ALGORITHM_SECONDS or peak_rss_mb >= 512.0:
                result["status"] = "RESOURCE_ABSTENTION"
            result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            results.append(result)

    results.sort(key=lambda item: item["review_id"])
    successful = [item for item in results if item.get("status") == "B1_COMPLETED"]
    times = sorted(item.get("algorithm_seconds", math.inf) for item in successful)
    p95_index = max(0, math.ceil(len(times) * 0.95) - 1)
    payload = {
        "schema_version": "goal7-phase-c-results-v1",
        "status": "COMPLETE_ASSOCIATION_ONLY",
        "source_hashes": {"phase_c_config": _sha256(config_path), "s1_results": _sha256(s1_results_path)},
        "contract": {
            "detection_rerun": False,
            "cleaning": False,
            "pixel_text_mask": False,
            "auto_accept": False,
        },
        "summary": {
            "page_count": len(assets),
            "local_b1_candidate_count": len(config["items"]),
            "completed_b1_count": len(successful),
            "nonempty_coarse_candidate_count": sum(item.get("nonempty_candidate", False) for item in successful),
            "worker_crash_count": sum(item.get("status") == "WORKER_CRASH" for item in results),
            "worker_timeout_count": sum(item.get("status") == "WORKER_TIMEOUT" for item in results),
            "resource_abstention_count": sum(item.get("status") == "RESOURCE_ABSTENTION" for item in results),
            "peak_rss_mb": max((item.get("peak_rss_mb", 0.0) for item in results), default=0.0),
            "p95_algorithm_seconds": times[p95_index] if times else 0.0,
            "page_global_extreme_abstention_count": 0,
            "page_global_topology_block_count": 0,
            "auto_accept_count": 0,
        },
        "results": results,
    }
    result_path = output_dir / "PHASE-C-RESULTS.json"
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _build_sample_contact_sheet(results, output_dir)
    return result_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Goal 7 frozen 40-page local B1 replay")
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--matrix", type=Path, required=True)
    freeze.add_argument("--phase-b-review", type=Path, required=True)
    freeze.add_argument("--s1-results", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--s1-results", type=Path, required=True)
    run.add_argument("--root", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "freeze":
        print(freeze_phase_c_config(args.matrix, args.phase_b_review, args.s1_results, args.output))
    elif args.command == "run":
        print(run_phase_c(args.config, args.s1_results, args.root, args.output_dir))


if __name__ == "__main__":
    main()
