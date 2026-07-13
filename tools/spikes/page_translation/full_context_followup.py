#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import random
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[3]
FOLLOWUP_ROOT = ROOT_DIR / "local_samples" / "page_translation" / "full_context_followup"
OUTPUT_ROOT = ROOT_DIR / "local_samples" / "spike_outputs" / "page-translation-full-context"
PARENT_SPIKE_PATH = ROOT_DIR / "tools" / "spikes" / "page_translation" / "spike.py"
PROMPT_PATH = ROOT_DIR / "prompts" / "page-translation" / "system-v1.md"
REPAIR_PROMPT_PATH = ROOT_DIR / "prompts" / "page-translation" / "repair-system-v1.md"
PARENT_SCHEMA_PATH = ROOT_DIR / "local_samples" / "page_translation" / "schema.json"
RANDOM_SEED = 20260710
STABILITY_TRIALS = 5
PAIRED_TRIALS = 3
TEMPERATURE = 0
MAX_OUTPUT_TOKENS = 1200
TIMEOUT_SEC_DEFAULT = 60.0
RUNTIME_FAILURES = {"HTTP_ERROR", "TIMEOUT", "EMPTY_BODY", "NO_CHOICES", "EMPTY_CONTENT", "PROVIDER_REFUSAL", "CLIENT_ERROR"}
EMPTY_RUNTIME_STATUSES = {"EMPTY_BODY", "NO_CHOICES", "EMPTY_CONTENT"}


class FollowupStop(Exception):
    pass


def load_parent_spike():
    spec = importlib.util.spec_from_file_location("page_translation_spike", PARENT_SPIKE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PARENT = load_parent_spike()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + os.urandom(3).hex()


def dumps_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise FollowupStop(f"JSON root must be object: {path}")
    return data


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def hash_json(data: Any) -> str:
    return sha256_text(dumps_json(data))


def write_text_checked(path: Path, text: str) -> None:
    assert_no_secret_text(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json_checked(path: Path, data: Any) -> None:
    write_text_checked(path, dumps_json(data))


def assert_no_secret_text(text: str) -> None:
    lowered = text.lower()
    if "authorization:" in lowered or "bearer " in lowered or ".env.page-translation.local" in lowered:
        raise FollowupStop("secret-like text would be written")
    key = os.environ.get("MRF_TRANSLATION_API_KEY", "")
    if key and key in text:
        raise FollowupStop("API key would be written")


def require_api_config() -> dict[str, str]:
    missing = [key for key in PARENT.REQUIRED_ENV if not os.environ.get(key)]
    if missing:
        raise FollowupStop("missing API configuration: " + ", ".join(missing))
    try:
        float(os.environ["MRF_TRANSLATION_TIMEOUT_SEC"])
    except ValueError as error:
        raise FollowupStop("MRF_TRANSLATION_TIMEOUT_SEC must be numeric") from error
    return {
        "base": os.environ["MRF_TRANSLATION_API_BASE"].strip().rstrip("/"),
        "key": os.environ["MRF_TRANSLATION_API_KEY"].strip(),
        "model": os.environ["MRF_TRANSLATION_MODEL"].strip(),
        "timeout": os.environ["MRF_TRANSLATION_TIMEOUT_SEC"],
    }


def generation_config(max_output_tokens: int = MAX_OUTPUT_TOKENS) -> dict[str, Any]:
    return {
        "temperature": TEMPERATURE,
        "max_output_tokens": max_output_tokens,
        "timeout_sec": TIMEOUT_SEC_DEFAULT,
    }


def git_value(args: list[str]) -> str:
    return subprocess.check_output(args, cwd=ROOT_DIR, text=True).strip()


def safe_provider_id(value: str | None) -> str:
    if not value:
        return ""
    return sha256_text(value)[:16]


def sanitize_raw_response(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    sanitized = json.loads(json.dumps(raw))
    if isinstance(sanitized.get("id"), str):
        sanitized["provider_request_id_hash"] = safe_provider_id(sanitized.pop("id"))
    return sanitized


def chat_url(base: str) -> str:
    return PARENT.chat_url(base)


def prompt_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    return PARENT.prompt_messages(PROMPT_PATH.read_text(encoding="utf-8"), payload)


def repair_messages(payload: dict[str, Any], original_response: str, errors: list[str]) -> list[dict[str, str]]:
    return PARENT.repair_messages(
        REPAIR_PROMPT_PATH.read_text(encoding="utf-8"),
        payload,
        original_response,
        load_json(PARENT_SCHEMA_PATH),
        errors,
    )


def call_api(config: dict[str, str], messages: list[dict[str, str]], *, max_output_tokens: int = MAX_OUTPUT_TOKENS) -> dict[str, Any]:
    request_payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": max_output_tokens,
    }
    body = json.dumps(request_payload).encode("utf-8")
    request = urllib.request.Request(
        chat_url(config["base"]),
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + config["key"]},
        method="POST",
    )
    start = time.time()
    try:
        with urllib.request.urlopen(request, timeout=float(config["timeout"])) as response:
            raw_bytes = response.read()
            http_status = response.status
    except urllib.error.HTTPError as error:
        return runtime_payload("HTTP_ERROR", int((time.time() - start) * 1000), http_status=error.code, raw={"error": "http_error"})
    except TimeoutError:
        return runtime_payload("TIMEOUT", int((time.time() - start) * 1000), raw={"error": "timeout"})
    except Exception as error:
        return runtime_payload("CLIENT_ERROR", int((time.time() - start) * 1000), raw={"error": type(error).__name__})

    latency_ms = int((time.time() - start) * 1000)
    if not raw_bytes:
        return runtime_payload("EMPTY_BODY", latency_ms, http_status=http_status, raw={})
    raw_text = raw_bytes.decode("utf-8", errors="ignore")
    assert_no_secret_text(raw_text)
    try:
        raw = json.loads(raw_bytes)
    except json.JSONDecodeError:
        return runtime_payload("CLIENT_ERROR", latency_ms, http_status=http_status, raw={"error": "non_json_body"})
    return classify_raw_response(raw, latency_ms, http_status)


def runtime_payload(runtime_status: str, latency_ms: int, *, http_status: int | None = None, raw: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "runtime_status": runtime_status,
        "http_status": http_status,
        "latency_ms": latency_ms,
        "response_body_present": bool(raw),
        "choices_count": 0,
        "content_present": False,
        "content_length": 0,
        "finish_reason": "",
        "usage_present": False,
        "input_tokens": None,
        "output_tokens": None,
        "provider_request_id": "",
        "content": "",
        "raw": raw or {},
    }


def classify_raw_response(raw: dict[str, Any], latency_ms: int = 0, http_status: int | None = 200) -> dict[str, Any]:
    choices = raw.get("choices")
    choices_count = len(choices) if isinstance(choices, list) else 0
    usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
    base = {
        "http_status": http_status,
        "latency_ms": latency_ms,
        "response_body_present": True,
        "choices_count": choices_count,
        "usage_present": bool(usage),
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "provider_request_id": safe_provider_id(raw.get("id") if isinstance(raw.get("id"), str) else None),
        "raw": sanitize_raw_response(raw),
    }
    if choices_count < 1:
        return {**base, "runtime_status": "NO_CHOICES", "content_present": False, "content_length": 0, "finish_reason": "", "content": ""}
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first.get("message"), dict) else {}
    content = message.get("content") if isinstance(message.get("content"), str) else first.get("text") if isinstance(first.get("text"), str) else ""
    finish_reason = first.get("finish_reason") if isinstance(first.get("finish_reason"), str) else ""
    if "refusal" in content.lower():
        return {**base, "runtime_status": "PROVIDER_REFUSAL", "content_present": True, "content_length": len(content), "finish_reason": finish_reason, "content": content}
    if not content.strip():
        return {**base, "runtime_status": "EMPTY_CONTENT", "content_present": bool(content), "content_length": len(content), "finish_reason": finish_reason, "content": content}
    return {**base, "runtime_status": "SUCCESS_RESPONSE", "content_present": True, "content_length": len(content), "finish_reason": finish_reason, "content": content}


def validate_structure(payload: dict[str, Any], content: str) -> dict[str, Any]:
    parsed, parse_errors = PARENT.parse_model_json(content)
    validation = PARENT.validate_translation_output(parsed, payload)
    if parse_errors:
        validation["errors"] = sorted(set(validation["errors"] + parse_errors))
        validation["valid"] = False
    return {"parsed": parsed, "validation": validation, "parse_errors": parse_errors}


def retryable_structure_errors(errors: list[str]) -> list[str]:
    return [error for error in errors if error in PARENT.RETRYABLE_ERRORS]


def process_trial(
    config: dict[str, str],
    trial: dict[str, Any],
    run_dir: Path,
    *,
    max_output_tokens: int = MAX_OUTPUT_TOKENS,
) -> dict[str, Any]:
    payload = trial["payload"]
    api = call_api(config, prompt_messages(payload), max_output_tokens=max_output_tokens)
    trial_id = trial["trial_id"]
    write_json_checked(run_dir / "raw_responses" / f"{trial_id}-first.json", api["raw"])
    record = build_trial_record(trial, api, attempt="first")
    if api["runtime_status"] != "SUCCESS_RESPONSE":
        return record

    structure = validate_structure(payload, api["content"])
    record["first_validation"] = structure["validation"]
    record["final_validation"] = structure["validation"]
    record["parsed"] = structure["parsed"]
    errors = retryable_structure_errors(structure["validation"]["errors"])
    if not errors:
        return record

    repair_api = call_api(config, repair_messages(payload, api["content"], errors), max_output_tokens=max_output_tokens)
    write_json_checked(run_dir / "raw_responses" / f"{trial_id}-repair.json", repair_api["raw"])
    record["repair_attempted"] = True
    record["repair_errors"] = errors
    if repair_api["runtime_status"] != "SUCCESS_RESPONSE":
        record["repair_failed"] = True
        return record
    repair_structure = validate_structure(payload, repair_api["content"])
    record["final_validation"] = repair_structure["validation"]
    record["parsed"] = repair_structure["parsed"]
    record["repair_recovered"] = repair_structure["validation"]["valid"]
    record["repair_failed"] = not repair_structure["validation"]["valid"]
    record["latency_ms"] += repair_api["latency_ms"]
    record["input_tokens"] = sum_optional(record.get("input_tokens"), repair_api.get("input_tokens"))
    record["output_tokens"] = sum_optional(record.get("output_tokens"), repair_api.get("output_tokens"))
    return record


def run_token_diagnostic(run_dir: Path) -> dict[str, Any]:
    records = all_records(run_dir)
    candidate = next(
        (
            record
            for record in records
            if record["runtime_status"] in EMPTY_RUNTIME_STATUSES
            and (record.get("finish_reason") == "length" or int(record.get("output_tokens") or 0) >= MAX_OUTPUT_TOKENS)
        ),
        None,
    )
    if not candidate:
        result = {"executed": False, "reason": "no_token_exhaustion_empty_response_candidate"}
        write_json_checked(run_dir / "token-diagnostic-results.json", result)
        return result
    trial = scheduled_trial_by_id(candidate["trial_id"])
    trial = dict(trial)
    trial["trial_id"] = f"TOKEN_DIAGNOSTIC-{candidate['trial_id']}"
    trial["experiment"] = "TOKEN_DIAGNOSTIC"
    trial["generation_config_hash"] = hash_json(generation_config(max_output_tokens=2400))
    record = process_trial(require_api_config(), trial, run_dir, max_output_tokens=2400)
    result = {
        "executed": True,
        "source_trial_id": candidate["trial_id"],
        "source_runtime_status": candidate["runtime_status"],
        "source_finish_reason": candidate.get("finish_reason"),
        "source_output_tokens": candidate.get("output_tokens"),
        "max_output_tokens": 2400,
        "record": record,
    }
    write_json_checked(run_dir / "token-diagnostic-results.json", result)
    return result


def scheduled_trial_by_id(trial_id: str) -> dict[str, Any]:
    for trial in stability_schedule() + paired_schedule():
        if trial["trial_id"] == trial_id:
            return trial
    raise FollowupStop(f"scheduled trial not found: {trial_id}")


def sum_optional(left: int | None, right: int | None) -> int | None:
    if left is None and right is None:
        return None
    return int(left or 0) + int(right or 0)


def build_trial_record(trial: dict[str, Any], api: dict[str, Any], *, attempt: str) -> dict[str, Any]:
    payload = trial["payload"]
    validation = PARENT.validation_payload(
        ["not_evaluable"],
        [block["text_block_id"] for block in payload["blocks"]],
        [],
        [],
        [],
        [],
        [],
    )
    validation["valid"] = False
    return {
        **{key: value for key, value in trial.items() if key != "payload"},
        "http_status": api["http_status"],
        "latency_ms": api["latency_ms"],
        "response_body_present": api["response_body_present"],
        "choices_count": api["choices_count"],
        "content_present": api["content_present"],
        "content_length": api["content_length"],
        "finish_reason": api["finish_reason"],
        "usage_present": api["usage_present"],
        "input_tokens": api["input_tokens"],
        "output_tokens": api["output_tokens"],
        "provider_request_id": api["provider_request_id"],
        "runtime_status": api["runtime_status"],
        "first_validation": validation,
        "final_validation": validation,
        "parsed": None,
        "repair_attempted": False,
        "repair_recovered": False,
        "repair_failed": False,
        "repair_errors": [],
    }


def current_page_payload(fixture: dict[str, Any]) -> dict[str, Any]:
    return {
        "page_id": fixture["current_page"]["page_id"],
        "source_language": fixture["current_page"]["source_language"],
        "target_language": fixture["current_page"]["target_language"],
        "blocks": sorted(fixture["current_page"]["blocks"], key=lambda block: block["reading_order"]),
    }


def pair_payload(fixture: dict[str, Any], group: str) -> dict[str, Any]:
    payload = current_page_payload(fixture)
    payload["glossary"] = fixture.get("glossary", [])
    payload["previous_context"] = fixture.get("previous_context", []) if group == "P" else []
    return payload


def pair_hashes(fixture: dict[str, Any], group: str) -> dict[str, str]:
    payload = pair_payload(fixture, group)
    current_payload = {key: payload[key] for key in ["page_id", "source_language", "target_language", "blocks"]}
    return {
        "request_hash": hash_json(payload),
        "current_page_hash": hash_json(current_payload),
        "glossary_hash": hash_json(fixture.get("glossary", [])),
        "previous_context_hash": hash_json(payload["previous_context"]),
        "prompt_hash": sha256_file(PROMPT_PATH),
        "schema_hash": sha256_file(PARENT_SCHEMA_PATH),
        "generation_config_hash": hash_json(generation_config()),
    }


def validate_pair_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    required = ["fixture_id", "current_page", "previous_context", "evaluation_focus"]
    missing = [key for key in required if key not in fixture]
    if missing:
        return {"valid": False, "errors": ["missing_" + key for key in missing]}
    blocks = fixture["current_page"].get("blocks", [])
    errors: list[str] = []
    if not 2 <= len(blocks) <= 8:
        errors.append("invalid_block_count")
    if not fixture.get("previous_context"):
        errors.append("empty_previous_context")
    previous_pages = {item.get("page_id") for item in fixture.get("previous_context", []) if isinstance(item, dict)}
    previous_pages.discard(None)
    if len(previous_pages) > 1 or len(fixture.get("previous_context", [])) > 20:
        errors.append("previous_context_bound")
    if any(item.get("status") not in {"accepted", "locked"} for item in fixture.get("previous_context", [])):
        errors.append("invalid_previous_status")
    n_hashes = pair_hashes(fixture, "N")
    p_hashes = pair_hashes(fixture, "P")
    for key in ["current_page_hash", "glossary_hash", "prompt_hash", "schema_hash", "generation_config_hash"]:
        if n_hashes[key] != p_hashes[key]:
            errors.append(f"{key}_mismatch")
    if n_hashes["previous_context_hash"] == p_hashes["previous_context_hash"]:
        errors.append("previous_context_hash_same")
    return {"valid": not errors, "errors": sorted(set(errors)), "N": n_hashes, "P": p_hashes}


def validate_np_only_differs_previous(fixture: dict[str, Any]) -> bool:
    n_payload = pair_payload(fixture, "N")
    p_payload = pair_payload(fixture, "P")
    n_without_prev = {key: value for key, value in n_payload.items() if key != "previous_context"}
    p_without_prev = {key: value for key, value in p_payload.items() if key != "previous_context"}
    return n_without_prev == p_without_prev and n_payload["previous_context"] != p_payload["previous_context"]


def load_manifest() -> dict[str, Any]:
    return load_json(FOLLOWUP_ROOT / "manifest.json")


def load_stability_payloads() -> list[tuple[str, dict[str, Any]]]:
    manifest = load_manifest()
    payloads = []
    for name in manifest.get("stability", []):
        path = FOLLOWUP_ROOT / "stability" / name
        payloads.append((Path(name).stem, load_json(path)))
    return payloads


def load_paired_fixtures() -> list[dict[str, Any]]:
    manifest = load_manifest()
    return [load_json(FOLLOWUP_ROOT / "paired" / name) for name in manifest.get("paired", [])]


def reference_for(fixture_id: str) -> dict[str, Any]:
    path = FOLLOWUP_ROOT / "references" / f"{fixture_id}.json"
    return load_json(path) if path.exists() else {"translations": []}


def validate_followup() -> dict[str, Any]:
    require_api_config()
    for path in [PROMPT_PATH, REPAIR_PROMPT_PATH, PARENT_SCHEMA_PATH, FOLLOWUP_ROOT / "manifest.json"]:
        if not path.exists() or not path.read_text(encoding="utf-8").strip():
            raise FollowupStop(f"missing or empty required file: {path}")
    stability = load_stability_payloads()
    if len(stability) != 3:
        raise FollowupStop("stability must contain exactly 3 payloads")
    for fixture_id, payload in stability:
        validate_input_payload(payload, fixture_id)
    paired = load_paired_fixtures()
    if len(paired) < 4:
        raise FollowupStop("paired fixture count must be at least 4")
    invalid = {fixture["fixture_id"]: validate_pair_fixture(fixture)["errors"] for fixture in paired if not validate_pair_fixture(fixture)["valid"]}
    if invalid:
        raise FollowupStop("invalid pair fixtures: " + dumps_json(invalid).strip())
    if any(reference_leak_detected(fixture) for fixture in paired):
        raise FollowupStop("reference leakage detected")
    manifest_hashes = fixture_hashes()
    return {
        "ok": True,
        "stability_payloads": len(stability),
        "paired_fixtures": len(paired),
        "system_prompt_sha256": sha256_file(PROMPT_PATH),
        "repair_prompt_sha256": sha256_file(REPAIR_PROMPT_PATH),
        "schema_sha256": sha256_file(PARENT_SCHEMA_PATH),
        "fixture_hashes": manifest_hashes,
        "fixture_set_sha256": hash_json(manifest_hashes),
        "random_seed": RANDOM_SEED,
    }


def validate_input_payload(payload: dict[str, Any], fixture_id: str) -> None:
    required = ["page_id", "source_language", "target_language", "blocks", "glossary", "previous_context"]
    missing = [key for key in required if key not in payload]
    if missing:
        raise FollowupStop(f"{fixture_id}: missing keys {missing}")
    block_ids: set[str] = set()
    orders: set[int] = set()
    for block in payload["blocks"]:
        if block["text_block_id"] in block_ids:
            raise FollowupStop(f"{fixture_id}: duplicate block id")
        block_ids.add(block["text_block_id"])
        if block["reading_order"] in orders:
            raise FollowupStop(f"{fixture_id}: duplicate reading order")
        orders.add(block["reading_order"])


def reference_leak_detected(fixture: dict[str, Any]) -> bool:
    ref = reference_for(fixture["fixture_id"])
    payload_texts = [dumps_json(pair_payload(fixture, group)) for group in ["N", "P"]]
    for item in ref.get("translations", []):
        translation = item.get("translation_text")
        if isinstance(translation, str) and translation and any(translation in payload for payload in payload_texts):
            return True
    return False


def fixture_hashes() -> dict[str, str]:
    paths = [FOLLOWUP_ROOT / "manifest.json"]
    paths += sorted((FOLLOWUP_ROOT / "stability").glob("*.json"))
    paths += sorted((FOLLOWUP_ROOT / "paired").glob("*.json"))
    paths += sorted((FOLLOWUP_ROOT / "references").glob("*.json"))
    return {str(path.relative_to(FOLLOWUP_ROOT)): sha256_file(path) for path in paths}


def stability_schedule(trials_per_payload: int = STABILITY_TRIALS) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for fixture_id, payload in load_stability_payloads():
        request_hash = hash_json(payload)
        for trial_index in range(1, trials_per_payload + 1):
            items.append(
                {
                    "experiment": "S",
                    "fixture_id": fixture_id,
                    "group": "S",
                    "trial_index": trial_index,
                    "trial_id": f"S-{fixture_id}-{trial_index:02d}",
                    "payload": payload,
                    "request_hash": request_hash,
                    "current_page_hash": hash_json({key: payload[key] for key in ["page_id", "source_language", "target_language", "blocks"]}),
                    "glossary_hash": hash_json(payload.get("glossary", [])),
                    "previous_context_hash": hash_json(payload.get("previous_context", [])),
                    "prompt_hash": sha256_file(PROMPT_PATH),
                    "schema_hash": sha256_file(PARENT_SCHEMA_PATH),
                    "generation_config_hash": hash_json(generation_config()),
                }
            )
    return shuffled(items, RANDOM_SEED)


def paired_schedule(trials_per_group: int = PAIRED_TRIALS) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for fixture in load_paired_fixtures():
        for group in ["N", "P"]:
            payload = pair_payload(fixture, group)
            hashes = pair_hashes(fixture, group)
            for trial_index in range(1, trials_per_group + 1):
                items.append(
                    {
                        "experiment": "NP",
                        "fixture_id": fixture["fixture_id"],
                        "group": group,
                        "trial_index": trial_index,
                        "trial_id": f"NP-{fixture['fixture_id']}-{group}-{trial_index:02d}",
                        "payload": payload,
                        "evaluation_focus": "|".join(fixture.get("evaluation_focus", [])),
                        **hashes,
                    }
                )
    return shuffled(items, RANDOM_SEED + 1)


def shuffled(items: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    copied = list(items)
    random.Random(seed).shuffle(copied)
    return copied


def create_run_dir() -> Path:
    run_dir = OUTPUT_ROOT / make_run_id()
    (run_dir / "raw_responses").mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    return run_dir


def load_or_create_metadata(run_dir: Path | None = None) -> tuple[Path, dict[str, Any]]:
    validation = validate_followup()
    config = require_api_config()
    if run_dir is None:
        run_dir = create_run_dir()
    run_id = run_dir.name
    metadata_path = run_dir / "metadata.json"
    if metadata_path.exists():
        metadata = load_json(metadata_path)
    else:
        metadata = {
            "run_id": run_id,
            "timestamp": utc_now(),
            "branch": git_value(["git", "branch", "--show-current"]),
            "git_head": git_value(["git", "rev-parse", "--short", "HEAD"]),
            "provider": "openai-compatible",
            "model": config["model"],
            "generation": generation_config(),
            **validation,
        }
        write_json_checked(metadata_path, metadata)
    return run_dir, metadata


def run_stability(run_dir: Path | None = None) -> Path:
    run_dir, _ = load_or_create_metadata(run_dir)
    config = require_api_config()
    records = [process_trial(config, trial, run_dir) for trial in stability_schedule()]
    write_json_checked(run_dir / "stability-results.json", {"records": records})
    write_trials_csv(run_dir)
    print(display_run_dir(run_dir))
    return run_dir


def run_paired(run_dir: Path | None = None) -> Path:
    if run_dir is None:
        run_dir = latest_run_dir()
    run_dir, _ = load_or_create_metadata(run_dir)
    config = require_api_config()
    records = [process_trial(config, trial, run_dir) for trial in paired_schedule()]
    write_json_checked(run_dir / "paired-results.json", {"records": records})
    write_trials_csv(run_dir)
    print(display_run_dir(run_dir))
    return run_dir


def display_run_dir(run_dir: Path) -> str:
    resolved = run_dir.resolve()
    try:
        return str(resolved.relative_to(ROOT_DIR))
    except ValueError:
        return str(run_dir)


def latest_run_dir() -> Path:
    candidates = sorted([path for path in OUTPUT_ROOT.glob("*") if path.is_dir()])
    if not candidates:
        raise FollowupStop("no run directory exists")
    return candidates[-1]


def all_records(run_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for name in ["stability-results.json", "paired-results.json"]:
        path = run_dir / name
        if path.exists():
            records.extend(load_json(path).get("records", []))
    return records


def write_trials_csv(run_dir: Path) -> None:
    records = all_records(run_dir)
    fields = [
        "trial_id",
        "experiment",
        "fixture_id",
        "group",
        "trial_index",
        "request_hash",
        "current_page_hash",
        "glossary_hash",
        "previous_context_hash",
        "http_status",
        "latency_ms",
        "response_body_present",
        "choices_count",
        "content_present",
        "content_length",
        "finish_reason",
        "usage_present",
        "input_tokens",
        "output_tokens",
        "provider_request_id",
        "runtime_status",
        "first_errors",
        "final_errors",
        "repair_attempted",
        "repair_recovered",
        "repair_failed",
    ]
    rows = []
    for record in records:
        rows.append(
            {
                **{field: record.get(field, "") for field in fields},
                "first_errors": "|".join(record.get("first_validation", {}).get("errors", [])),
                "final_errors": "|".join(record.get("final_validation", {}).get("errors", [])),
            }
        )
    write_csv(run_dir / "trials.csv", fields, rows)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    write_text_checked(path, buffer.getvalue())


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as file_obj:
        return list(csv.DictReader(file_obj))


def verify_run(run_dir: Path) -> dict[str, Any]:
    metadata = load_json(run_dir / "metadata.json")
    current = validate_followup()
    for key in ["system_prompt_sha256", "repair_prompt_sha256", "schema_sha256", "fixture_set_sha256"]:
        if metadata[key] != current[key]:
            raise FollowupStop(f"frozen input hash changed: {key}")
    records = all_records(run_dir)
    if len([record for record in records if record["experiment"] == "S"]) not in {0, 15}:
        raise FollowupStop("stability trial count invalid")
    if len([record for record in records if record["experiment"] == "NP"]) not in {0, len(load_paired_fixtures()) * 2 * PAIRED_TRIALS}:
        raise FollowupStop("paired trial count invalid")
    for record in records:
        if record.get("repair_attempted") and record["runtime_status"] in RUNTIME_FAILURES:
            raise FollowupStop("runtime failure attempted repair")
        if (run_dir / "raw_responses" / f"{record['trial_id']}-repair.json").exists() and not record.get("repair_attempted"):
            raise FollowupStop("unexpected repair response file")
    validate_pair_hashes()
    scan_output_for_secrets(run_dir)
    return {"ok": True}


def validate_pair_hashes() -> None:
    invalid = {fixture["fixture_id"]: validate_pair_fixture(fixture)["errors"] for fixture in load_paired_fixtures() if not validate_pair_fixture(fixture)["valid"]}
    if invalid:
        raise FollowupStop("invalid pair hashes: " + dumps_json(invalid).strip())


def scan_output_for_secrets(run_dir: Path) -> None:
    for path in run_dir.rglob("*"):
        if path.is_file():
            assert_no_secret_text(path.read_text(encoding="utf-8", errors="ignore"))


def summarize_run(run_dir: Path) -> dict[str, Any]:
    records = all_records(run_dir)
    stability_records = [record for record in records if record["experiment"] == "S"]
    paired_records = [record for record in records if record["experiment"] == "NP"]
    summary = {
        "run_id": run_dir.name,
        "stability": summarize_stability(stability_records),
        "paired": summarize_paired(paired_records),
        "structure": summarize_structure(paired_records),
    }
    diagnostic_path = run_dir / "token-diagnostic-results.json"
    if diagnostic_path.exists():
        summary["token_diagnostic"] = load_json(diagnostic_path)
    summary["empty_response_attribution"] = decide_empty_attribution(summary)
    summary["mvp_previous_context_policy"] = decide_previous_context_policy(summary)
    summary["overall_verdict"] = decide_overall_verdict(summary)
    write_json_checked(run_dir / "summary.json", summary)
    write_pair_comparisons(run_dir, paired_records)
    write_ratings(run_dir, paired_records)
    return summary


def summarize_stability(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_fixture: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_fixture.setdefault(record["fixture_id"], []).append(record)
    result = {}
    for fixture_id, rows in by_fixture.items():
        success = count_status(rows, "SUCCESS_RESPONSE")
        empty = sum(1 for row in rows if row["runtime_status"] in EMPTY_RUNTIME_STATUSES)
        result[fixture_id] = {
            "trial_count": len(rows),
            "request_hashes": sorted({row["request_hash"] for row in rows}),
            "success_count": success,
            "empty_response_count": empty,
            "empty_content_count": count_status(rows, "EMPTY_CONTENT"),
            "no_choices_count": count_status(rows, "NO_CHOICES"),
            "timeout_count": count_status(rows, "TIMEOUT"),
            "http_error_count": count_status(rows, "HTTP_ERROR"),
            "mixed_outcome": success > 0 and empty > 0,
            "median_latency_ms": median([row["latency_ms"] for row in rows]),
        }
    return result


def summarize_paired(records: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for group in ["N", "P"]:
        rows = [record for record in records if record["group"] == group]
        calls = len(rows)
        success = count_status(rows, "SUCCESS_RESPONSE")
        empty = sum(1 for row in rows if row["runtime_status"] in EMPTY_RUNTIME_STATUSES)
        valid = sum(1 for row in rows if row["runtime_status"] == "SUCCESS_RESPONSE" and row["final_validation"]["valid"])
        result[group] = {
            "calls": calls,
            "success": success,
            "empty_response": empty,
            "timeout": count_status(rows, "TIMEOUT"),
            "http_error": count_status(rows, "HTTP_ERROR"),
            "response_success_rate": rate(success, calls),
            "empty_response_rate": rate(empty, calls),
            "end_to_end_valid_response_rate": rate(valid, calls),
            "median_latency_ms": median([row["latency_ms"] for row in rows]),
            "max_latency_ms": max([row["latency_ms"] for row in rows], default=0),
            "input_tokens": sum(row.get("input_tokens") or 0 for row in rows),
            "output_tokens": sum(row.get("output_tokens") or 0 for row in rows),
        }
    return result


def summarize_structure(records: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for group in ["N", "P"]:
        rows = [record for record in records if record["group"] == group and record["runtime_status"] == "SUCCESS_RESPONSE"]
        expected = sum(record["final_validation"]["expected_block_count"] for record in rows)
        matched = sum(record["final_validation"]["matched_block_count"] for record in rows)
        result[group] = {
            "successful_response_count": len(rows),
            "first_pass_json_valid_rate": rate(sum("invalid_json" not in record["first_validation"]["errors"] for record in rows), len(rows)),
            "first_pass_schema_valid_rate": rate(sum(record["first_validation"]["valid"] for record in rows), len(rows)),
            "final_schema_valid_rate": rate(sum(record["final_validation"]["valid"] for record in rows), len(rows)),
            "block_mapping_coverage": rate(matched, expected),
            "missing_block_count": sum(1 for record in rows if "missing_block" in record["final_validation"]["errors"]),
            "duplicate_block_count": sum(1 for record in rows if "duplicate_block" in record["final_validation"]["errors"]),
            "unknown_block_count": sum(1 for record in rows if "unknown_block" in record["final_validation"]["errors"]),
            "repair_attempted": sum(1 for record in rows if record["repair_attempted"]),
            "repair_recovered": sum(1 for record in rows if record["repair_recovered"]),
            "repair_failed": sum(1 for record in rows if record["repair_failed"]),
        }
    return result


def count_status(rows: list[dict[str, Any]], status: str) -> int:
    return sum(1 for row in rows if row["runtime_status"] == status)


def rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def median(values: list[int]) -> int:
    return int(statistics.median(values)) if values else 0


def decide_empty_attribution(summary: dict[str, Any]) -> str:
    if any(item["mixed_outcome"] for item in summary["stability"].values()):
        return "PROVIDER_RANDOM"
    n_empty = summary["paired"].get("N", {}).get("empty_response", 0)
    p_empty = summary["paired"].get("P", {}).get("empty_response", 0)
    if n_empty == 0 and p_empty == 0 and all(item["empty_response_count"] == 0 for item in summary["stability"].values()):
        return "NOT_REPRODUCED"
    if p_empty > n_empty and p_empty >= 2:
        return "CONTEXT_ASSOCIATED"
    if n_empty or p_empty:
        return "INCONCLUSIVE"
    return "INCONCLUSIVE"


def decide_previous_context_policy(summary: dict[str, Any]) -> str:
    if summary["empty_response_attribution"] == "CONTEXT_ASSOCIATED":
        return "DISABLE_FOR_MVP"
    if summary["empty_response_attribution"] in {"PROVIDER_RANDOM", "INCONCLUSIVE"}:
        return "UNDECIDED"
    return "ENABLE_AS_OPTIONAL"


def decide_overall_verdict(summary: dict[str, Any]) -> str:
    if min(summary["structure"]["N"]["final_schema_valid_rate"], summary["structure"]["P"]["final_schema_valid_rate"]) < 1.0:
        return "FURTHER_SPIKE"
    if min(summary["structure"]["N"]["block_mapping_coverage"], summary["structure"]["P"]["block_mapping_coverage"]) < 1.0:
        return "FURTHER_SPIKE"
    if summary["empty_response_attribution"] == "CONTEXT_ASSOCIATED":
        return "NO_GO"
    if summary["empty_response_attribution"] in {"PROVIDER_RANDOM", "INCONCLUSIVE"}:
        return "FURTHER_SPIKE"
    return "CONDITIONAL_GO"


def write_pair_comparisons(run_dir: Path, records: list[dict[str, Any]]) -> None:
    fields = ["fixture_id", "text_block_id", "trial_index", "N_translation", "P_translation", "reference", "evaluation_focus", "runtime_status"]
    rows = []
    references = {fixture["fixture_id"]: reference_for(fixture["fixture_id"]) for fixture in load_paired_fixtures()}
    for fixture in load_paired_fixtures():
        for trial_index in range(1, PAIRED_TRIALS + 1):
            n = find_record(records, fixture["fixture_id"], "N", trial_index)
            p = find_record(records, fixture["fixture_id"], "P", trial_index)
            ref_by_id = {item["text_block_id"]: item.get("translation_text", "") for item in references[fixture["fixture_id"]].get("translations", [])}
            for block in fixture["current_page"]["blocks"]:
                block_id = block["text_block_id"]
                rows.append(
                    {
                        "fixture_id": fixture["fixture_id"],
                        "text_block_id": block_id,
                        "trial_index": trial_index,
                        "N_translation": translation_for(n, block_id),
                        "P_translation": translation_for(p, block_id),
                        "reference": ref_by_id.get(block_id, ""),
                        "evaluation_focus": "|".join(fixture.get("evaluation_focus", [])),
                        "runtime_status": f"N={n.get('runtime_status') if n else 'MISSING'};P={p.get('runtime_status') if p else 'MISSING'}",
                    }
                )
    write_csv(run_dir / "pair-comparisons.csv", fields, rows)


def write_ratings(run_dir: Path, records: list[dict[str, Any]]) -> None:
    fields = ["fixture_id", "group", "trial_index", "text_block_id", "quality_rating", "context_effect", "unsupported_disambiguation", "context_pollution", "note"]
    rows = []
    fixture_by_id = {fixture["fixture_id"]: fixture for fixture in load_paired_fixtures()}
    for record in records:
        fixture = fixture_by_id[record["fixture_id"]]
        for block in fixture["current_page"]["blocks"]:
            if record["runtime_status"] != "SUCCESS_RESPONSE" or not record["final_validation"]["valid"]:
                quality = "NO_OUTPUT"
                note = "runtime_or_structure_not_evaluable"
            else:
                quality = "NOT_EVALUABLE"
                note = "pending_independent_review"
            rows.append(
                {
                    "fixture_id": record["fixture_id"],
                    "group": record["group"],
                    "trial_index": record["trial_index"],
                    "text_block_id": block["text_block_id"],
                    "quality_rating": quality,
                    "context_effect": "PENDING_REVIEW",
                    "unsupported_disambiguation": False,
                    "context_pollution": False,
                    "note": note,
                }
            )
    write_csv(run_dir / "ratings.csv", fields, rows)


def find_record(records: list[dict[str, Any]], fixture_id: str, group: str, trial_index: int) -> dict[str, Any] | None:
    for record in records:
        if record["fixture_id"] == fixture_id and record["group"] == group and record["trial_index"] == trial_index:
            return record
    return None


def translation_for(record: dict[str, Any] | None, block_id: str) -> str:
    if not record or not record.get("parsed") or not record["final_validation"]["valid"]:
        return ""
    for item in record["parsed"].get("translations", []):
        if isinstance(item, dict) and item.get("text_block_id") == block_id:
            return item.get("translation_text", "")
    return ""


def print_json(data: Any) -> None:
    text = dumps_json(data)
    assert_no_secret_text(text)
    print(text, end="")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    stability_parser = sub.add_parser("run-stability")
    stability_parser.add_argument("--run-dir")
    paired_parser = sub.add_parser("run-paired")
    paired_parser.add_argument("--run-dir")
    diagnostic_parser = sub.add_parser("run-token-diagnostic")
    diagnostic_parser.add_argument("--run-dir", required=True)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--run-dir", required=True)
    summarize_parser = sub.add_parser("summarize")
    summarize_parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            print_json(validate_followup())
        elif args.command == "run-stability":
            run_stability(Path(args.run_dir) if args.run_dir else None)
        elif args.command == "run-paired":
            run_paired(Path(args.run_dir) if args.run_dir else None)
        elif args.command == "run-token-diagnostic":
            print_json(run_token_diagnostic(Path(args.run_dir)))
        elif args.command == "verify":
            print_json(verify_run(Path(args.run_dir)))
        elif args.command == "summarize":
            print_json(summarize_run(Path(args.run_dir)))
    except (FollowupStop, PARENT.SpikeStop) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
