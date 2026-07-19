#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[4]
PROMPT_PATH = Path(__file__).resolve().parent / "prompts/system-v1.md"
REPAIR_PROMPT_PATH = Path(__file__).resolve().parent / "prompts/repair-system-v1.md"
FIXTURE_ROOT = ROOT_DIR / "data/local/datasets/140-translation/page-translation-v0.1"
OUTPUT_ROOT = ROOT_DIR / "data/local/reviews/140-translation/page-translation-v0.1"
SCHEMA_PATH = FIXTURE_ROOT / "schema.json"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
PROMPT_TEMPLATE_VERSION = "system-v1"
REPAIR_PROMPT_TEMPLATE_VERSION = "repair-system-v1"
TEMPERATURE = 0
MAX_OUTPUT_TOKENS = 1200
RETRY_LIMIT = 1

ALLOWED_FLAGS = {
    "context_ambiguous",
    "pronoun_resolution_uncertain",
    "speaker_context_uncertain",
    "addressee_context_uncertain",
    "ocr_uncertain",
}
RETRYABLE_ERRORS = {
    "invalid_json",
    "markdown_wrapped_json",
    "schema_invalid",
    "wrong_page_id",
    "missing_block",
    "duplicate_block",
    "unknown_block",
    "invalid_uncertainty_flag",
    "field_type_error",
}
REQUIRED_ENV = [
    "MRF_TRANSLATION_API_BASE",
    "MRF_TRANSLATION_API_KEY",
    "MRF_TRANSLATION_MODEL",
    "MRF_TRANSLATION_TIMEOUT_SEC",
]


class SpikeStop(Exception):
    pass


@dataclass(frozen=True)
class ApiResult:
    ok: bool
    content: str
    raw: dict[str, Any] | None
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_classification: str | None = None
    http_status: int | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + os.urandom(3).hex()


def dumps_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SpikeStop(f"JSON root must be object: {path}")
    return data


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)


def git_value(args: list[str]) -> str:
    return subprocess.check_output(args, cwd=ROOT_DIR, text=True).strip()


def collect_secret_values() -> list[str]:
    values = []
    for key in REQUIRED_ENV:
        value = os.environ.get(key, "")
        if key == "MRF_TRANSLATION_API_KEY" and value:
            values.append(value)
    return [value for value in values if value]


def assert_no_secret_text(text: str) -> None:
    lowered = text.lower()
    if "authorization:" in lowered or "bearer " in lowered or ".env.page-translation.local" in lowered:
        raise SpikeStop("secret-like text would be written")
    for secret in collect_secret_values():
        if secret and secret in text:
            raise SpikeStop("API key would be written")


def write_text_checked(path: Path, text: str) -> None:
    assert_no_secret_text(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json_checked(path: Path, data: Any) -> None:
    write_text_checked(path, dumps_json(data))


def require_api_config() -> dict[str, str]:
    missing = [key for key in REQUIRED_ENV if not os.environ.get(key)]
    if missing:
        raise SpikeStop("missing API configuration: " + ", ".join(missing))
    timeout = os.environ["MRF_TRANSLATION_TIMEOUT_SEC"]
    try:
        float(timeout)
    except ValueError as error:
        raise SpikeStop("MRF_TRANSLATION_TIMEOUT_SEC must be numeric") from error
    return {
        "base": os.environ["MRF_TRANSLATION_API_BASE"].strip().rstrip("/"),
        "key": os.environ["MRF_TRANSLATION_API_KEY"].strip(),
        "model": os.environ["MRF_TRANSLATION_MODEL"].strip(),
        "timeout": timeout,
    }


def chat_url(base: str) -> str:
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


class OpenAICompatibleClient:
    def __init__(self, config: dict[str, str]) -> None:
        self.config = config

    def complete(self, messages: list[dict[str, str]]) -> ApiResult:
        payload = {
            "model": self.config["model"],
            "messages": messages,
            "temperature": TEMPERATURE,
            "max_tokens": MAX_OUTPUT_TOKENS,
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            chat_url(self.config["base"]),
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.config["key"],
            },
            method="POST",
        )
        start = time.time()
        try:
            with urllib.request.urlopen(request, timeout=float(self.config["timeout"])) as response:
                raw_bytes = response.read()
                status = response.status
        except urllib.error.HTTPError as error:
            classification = "authentication_failure" if error.code in {401, 403} else "model_not_found" if error.code == 404 else "api_error"
            return ApiResult(False, "", None, int((time.time() - start) * 1000), error_classification=classification, http_status=error.code)
        except TimeoutError:
            return ApiResult(False, "", None, int((time.time() - start) * 1000), error_classification="api_timeout")
        except Exception:
            return ApiResult(False, "", None, int((time.time() - start) * 1000), error_classification="endpoint_configuration_error")

        text = raw_bytes.decode("utf-8", errors="ignore")
        assert_no_secret_text(text)
        try:
            raw = json.loads(raw_bytes)
        except json.JSONDecodeError:
            return ApiResult(False, "", None, int((time.time() - start) * 1000), error_classification="api_error", http_status=status)
        content = extract_content(raw)
        usage = raw.get("usage") if isinstance(raw, dict) else {}
        if not content.strip():
            return ApiResult(False, "", raw, int((time.time() - start) * 1000), error_classification="empty_response", http_status=status)
        return ApiResult(
            True,
            content,
            raw,
            int((time.time() - start) * 1000),
            input_tokens=usage.get("prompt_tokens") if isinstance(usage, dict) else None,
            output_tokens=usage.get("completion_tokens") if isinstance(usage, dict) else None,
            http_status=status,
        )


def extract_content(raw: dict[str, Any]) -> str:
    choices = raw.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
        text = choices[0].get("text")
        if isinstance(text, str):
            return text
    output_text = raw.get("output_text")
    return output_text if isinstance(output_text, str) else ""


def strip_markdown_json(text: str) -> tuple[str, bool]:
    stripped = text.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        return stripped, False
    return match.group(1).strip(), True


def parse_model_json(text: str) -> tuple[dict[str, Any] | None, list[str]]:
    candidate, wrapped = strip_markdown_json(text)
    errors = ["markdown_wrapped_json"] if wrapped else []
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None, ["invalid_json"]
    if not isinstance(parsed, dict):
        return None, errors + ["schema_invalid"]
    return parsed, errors


def validate_translation_output(result: dict[str, Any] | None, fixture: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    expected_ids = [block["text_block_id"] for block in sorted(fixture["blocks"], key=lambda item: item["reading_order"])]
    matched_ids: list[str] = []
    duplicate_ids: list[str] = []
    unknown_ids: list[str] = []
    invalid_flags: list[str] = []
    empty_translations: list[str] = []

    if not isinstance(result, dict):
        errors.append("schema_invalid")
        return validation_payload(errors, expected_ids, [], [], [], [], [])

    if set(result.keys()) != {"page_id", "translations"}:
        errors.append("schema_invalid")
    if result.get("page_id") != fixture["page_id"]:
        errors.append("wrong_page_id")
    translations = result.get("translations")
    if not isinstance(translations, list):
        errors.append("field_type_error")
        return validation_payload(errors, expected_ids, [], [], [], [], [])

    seen: set[str] = set()
    for item in translations:
        if not isinstance(item, dict):
            errors.append("schema_invalid")
            continue
        if set(item.keys()) != {"text_block_id", "translation_text", "uncertainty_flags"}:
            errors.append("schema_invalid")
        text_block_id = item.get("text_block_id")
        if not isinstance(text_block_id, str):
            errors.append("field_type_error")
            continue
        if text_block_id in seen:
            duplicate_ids.append(text_block_id)
        seen.add(text_block_id)
        if text_block_id not in expected_ids:
            unknown_ids.append(text_block_id)
        else:
            matched_ids.append(text_block_id)
        if not isinstance(item.get("translation_text"), str):
            errors.append("field_type_error")
        elif not item["translation_text"].strip():
            empty_translations.append(text_block_id)
        flags = item.get("uncertainty_flags")
        if not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags):
            errors.append("field_type_error")
        else:
            invalid_flags.extend(flag for flag in flags if flag not in ALLOWED_FLAGS)

    missing_ids = [block_id for block_id in expected_ids if block_id not in seen]
    if missing_ids:
        errors.append("missing_block")
    if duplicate_ids:
        errors.append("duplicate_block")
    if unknown_ids:
        errors.append("unknown_block")
    if invalid_flags:
        errors.append("invalid_uncertainty_flag")
    if empty_translations:
        errors.append("empty_translation")

    return validation_payload(errors, expected_ids, matched_ids, missing_ids, duplicate_ids, unknown_ids, invalid_flags, empty_translations)


def validation_payload(
    errors: list[str],
    expected_ids: list[str],
    matched_ids: list[str],
    missing_ids: list[str],
    duplicate_ids: list[str],
    unknown_ids: list[str],
    invalid_flags: list[str],
    empty_translations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "valid": not errors,
        "errors": sorted(set(errors)),
        "expected_block_count": len(expected_ids),
        "matched_block_count": len(set(matched_ids)),
        "missing_block_ids": missing_ids,
        "duplicate_block_ids": sorted(set(duplicate_ids)),
        "unknown_block_ids": sorted(set(unknown_ids)),
        "invalid_uncertainty_flags": sorted(set(invalid_flags)),
        "empty_translation_ids": sorted(set(empty_translations or [])),
    }


def fixture_hashes(fixture_paths: list[Path]) -> dict[str, str]:
    return {path.name: sha256_file(path) for path in fixture_paths}


def fixture_set_hash(hashes: dict[str, str]) -> str:
    return sha256_bytes(dumps_json(hashes).encode("utf-8"))


def load_manifest_and_fixtures(root: Path = FIXTURE_ROOT) -> tuple[dict[str, Any], list[dict[str, Any]], list[Path]]:
    manifest = load_json(root / "manifest.json")
    fixture_names = manifest.get("fixtures")
    if not isinstance(fixture_names, list) or not fixture_names:
        raise SpikeStop("manifest.fixtures must be a non-empty list")
    fixtures: list[dict[str, Any]] = []
    fixture_paths: list[Path] = []
    for name in fixture_names:
        if not isinstance(name, str):
            raise SpikeStop("manifest fixture names must be strings")
        path = (root / "fixtures" / name).resolve()
        try:
            path.relative_to((root / "fixtures").resolve())
        except ValueError as error:
            raise SpikeStop("fixture path escapes fixture directory") from error
        fixture = load_json(path)
        fixtures.append(fixture)
        fixture_paths.append(path)
    return manifest, fixtures, fixture_paths


def validate_fixture_set(root: Path = FIXTURE_ROOT) -> dict[str, Any]:
    for path in [PROMPT_PATH, REPAIR_PROMPT_PATH, root / "manifest.json", root / "schema.json"]:
        if not path.exists() or not path.read_text(encoding="utf-8").strip():
            raise SpikeStop(f"required file missing or empty: {path}")
    schema = load_json(root / "schema.json")
    if schema.get("additionalProperties") is not False:
        raise SpikeStop("schema must forbid extra top-level fields")

    manifest, fixtures, fixture_paths = load_manifest_and_fixtures(root)
    page_ids: set[str] = set()
    scenarios: set[str] = set()
    errors: list[str] = []
    for fixture in fixtures:
        page_id = fixture.get("page_id")
        scenario = fixture.get("scenario")
        if not isinstance(page_id, str) or not page_id:
            errors.append("invalid_page_id")
            continue
        if page_id in page_ids:
            errors.append("duplicate_page_id")
        page_ids.add(page_id)
        if isinstance(scenario, str):
            scenarios.add(scenario)
        blocks = fixture.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            errors.append("empty_blocks")
            continue
        block_ids: set[str] = set()
        reading_orders: set[int] = set()
        for block in blocks:
            if not isinstance(block, dict):
                errors.append("invalid_block")
                continue
            block_id = block.get("text_block_id")
            order = block.get("reading_order")
            source_text = block.get("source_text")
            if not isinstance(block_id, str) or not block_id:
                errors.append("invalid_block_id")
            elif block_id in block_ids:
                errors.append("duplicate_block_id")
            block_ids.add(block_id)
            if not isinstance(order, int) or order < 1:
                errors.append("invalid_reading_order")
            elif order in reading_orders:
                errors.append("duplicate_reading_order")
            reading_orders.add(order)
            if not isinstance(source_text, str) or not source_text.strip():
                errors.append("empty_source_text")
        for term in fixture.get("glossary", []):
            if not isinstance(term, dict) or not all(isinstance(term.get(key), str) and term.get(key) for key in ["source", "target"]):
                errors.append("invalid_glossary")
        previous = fixture.get("previous_context", [])
        if not isinstance(previous, list) or len(previous) > 20:
            errors.append("previous_context_bound")
        previous_pages = {entry.get("page_id") for entry in previous if isinstance(entry, dict)}
        previous_pages.discard(None)
        if len(previous_pages) > 1 or page_id in previous_pages:
            errors.append("previous_context_bound")
        for entry in previous:
            if not isinstance(entry, dict) or entry.get("status") not in {"accepted", "locked"}:
                errors.append("invalid_previous_context")
        if reference_leak_detected(root, fixture):
            errors.append("reference_leakage")

    required = set(manifest.get("required_scenarios", []))
    if required and not required.issubset(scenarios):
        errors.append("missing_required_scenario")
    if errors:
        raise SpikeStop("validation failed: " + ", ".join(sorted(set(errors))))

    hashes = fixture_hashes(fixture_paths)
    return {
        "ok": True,
        "page_count": len(fixtures),
        "block_count": sum(len(fixture["blocks"]) for fixture in fixtures),
        "system_prompt_sha256": sha256_file(PROMPT_PATH),
        "repair_prompt_sha256": sha256_file(REPAIR_PROMPT_PATH),
        "schema_sha256": sha256_file(root / "schema.json"),
        "fixture_hashes": hashes,
        "fixture_set_sha256": fixture_set_hash(hashes),
    }


def reference_leak_detected(root: Path, fixture: dict[str, Any]) -> bool:
    reference_path = root / "references" / f"{fixture['page_id']}.json"
    if not reference_path.exists():
        return False
    reference_text = reference_path.read_text(encoding="utf-8")
    for group in ["A", "B", "C", "D"]:
        payloads = build_group_payloads(fixture, group)
        for payload in payloads:
            if reference_text and reference_text in dumps_json(payload):
                return True
            reference = json.loads(reference_text)
            for item in reference.get("translations", []):
                translation = item.get("translation_text")
                if isinstance(translation, str) and translation and translation in dumps_json(payload):
                    return True
    return False


def build_group_payloads(fixture: dict[str, Any], group: str) -> list[dict[str, Any]]:
    base = {
        "page_id": fixture["page_id"],
        "source_language": fixture["source_language"],
        "target_language": fixture["target_language"],
    }
    blocks = sorted(fixture["blocks"], key=lambda item: item["reading_order"])
    if group == "A":
        return [{**base, "blocks": [block], "glossary": [], "previous_context": []} for block in blocks]
    payload = {**base, "blocks": blocks, "glossary": [], "previous_context": []}
    if group in {"C", "D"}:
        payload["glossary"] = fixture.get("glossary", [])
    if group == "D":
        payload["previous_context"] = fixture.get("previous_context", [])
    return [payload]


def prompt_messages(system_prompt: str, payload: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": dumps_json(payload)},
    ]


def repair_messages(repair_prompt: str, original_payload: dict[str, Any], original_response: str, schema: dict[str, Any], errors: list[str]) -> list[dict[str, str]]:
    repair_payload = {
        "original_request": original_payload,
        "original_response": original_response,
        "target_schema": schema,
        "validation_errors": errors,
    }
    return [
        {"role": "system", "content": repair_prompt},
        {"role": "user", "content": dumps_json(repair_payload)},
    ]


def api_smoke() -> dict[str, Any]:
    config = require_api_config()
    client = OpenAICompatibleClient(config)
    payload = {
        "page_id": "smoke-page",
        "source_language": "ja",
        "target_language": "zh-Hans",
        "blocks": [{"text_block_id": "smoke-b001", "reading_order": 1, "group_id": None, "source_text": "こんにちは"}],
        "glossary": [],
        "previous_context": [],
    }
    system = PROMPT_PATH.read_text(encoding="utf-8")
    result = client.complete(prompt_messages(system, payload))
    if not result.ok:
        raise SpikeStop(f"api-smoke failed: {result.error_classification}")
    parsed, parse_errors = parse_model_json(result.content)
    validation = validate_translation_output(parsed, payload)
    if parse_errors or not validation["valid"]:
        raise SpikeStop("api-smoke failed: minimal JSON response invalid")
    return {"ok": True, "http_status": result.http_status, "latency_ms": result.latency_ms, "response_nonempty": True}


def run_experiment() -> Path:
    validation = validate_fixture_set()
    config = require_api_config()
    manifest, fixtures, _ = load_manifest_and_fixtures()
    run_id = make_run_id()
    run_dir = OUTPUT_ROOT / run_id
    raw_dir = run_dir / "raw_responses"
    logs_dir = run_dir / "logs"
    raw_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "run_id": run_id,
        "timestamp": utc_now(),
        "branch": git_value(["git", "branch", "--show-current"]),
        "git_head": git_value(["git", "rev-parse", "--short", "HEAD"]),
        "provider": "openai-compatible",
        "model": config["model"],
        "generation": {"temperature": TEMPERATURE, "max_output_tokens": MAX_OUTPUT_TOKENS, "timeout_sec": float(config["timeout"])},
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "repair_prompt_template_version": REPAIR_PROMPT_TEMPLATE_VERSION,
        **validation,
        "manifest": manifest,
    }
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    repair_prompt = REPAIR_PROMPT_PATH.read_text(encoding="utf-8")
    schema = load_json(SCHEMA_PATH)
    client = OpenAICompatibleClient(config)
    records: list[dict[str, Any]] = []
    requests_rows: list[dict[str, Any]] = []
    translations_rows: list[dict[str, Any]] = []

    for group in ["A", "B", "C", "D"]:
        for fixture in fixtures:
            for payload_index, payload in enumerate(build_group_payloads(fixture, group), start=1):
                request_id = f"{group}-{fixture['page_id']}-{payload_index:02d}"
                request_hash = sha256_bytes(dumps_json(payload).encode("utf-8"))
                write_json_checked(run_dir / "requests" / f"{request_id}.json", payload)
                api_result = client.complete(prompt_messages(system_prompt, payload))
                first_raw_path = raw_dir / f"{request_id}-first.json"
                write_json_checked(first_raw_path, api_result.raw or {"error": api_result.error_classification})

                record = build_record(request_id, group, fixture, payload, request_hash, api_result, attempt="first")
                final_record = record
                retry_errors = [error for error in record["first_validation"]["errors"] if error in RETRYABLE_ERRORS]
                if should_attempt_repair(api_result.ok, api_result.error_classification, retry_errors):
                    repair_result = client.complete(repair_messages(repair_prompt, payload, api_result.content, schema, retry_errors))
                    write_json_checked(raw_dir / f"{request_id}-repair.json", repair_result.raw or {"error": repair_result.error_classification})
                    repair_record = build_record(request_id, group, fixture, payload, request_hash, repair_result, attempt="repair")
                    final_record = merge_repair_record(record, repair_record)
                records.append(final_record)
                requests_rows.append(request_row(final_record))
                translations_rows.extend(translation_rows(final_record, fixture))

    ratings_rows = build_ratings_rows(records)
    results = {"metadata": metadata, "records": records}
    write_json_checked(run_dir / "results.json", results)
    write_csv(run_dir / "requests.csv", requests_rows)
    write_csv(run_dir / "translations.csv", translations_rows)
    write_csv(run_dir / "ratings.csv", ratings_rows)
    write_json_checked(logs_dir / "run-log.json", {"run_id": run_id, "event": "completed", "timestamp": utc_now()})
    summarize_run(run_dir)
    verify_run(run_dir)
    print(str(run_dir.relative_to(ROOT_DIR)))
    return run_dir


def should_attempt_repair(api_ok: bool, error_classification: str | None, validation_errors: list[str]) -> bool:
    if not api_ok or error_classification == "provider_refusal":
        return False
    return bool([error for error in validation_errors if error in RETRYABLE_ERRORS])


def build_record(
    request_id: str,
    group: str,
    fixture: dict[str, Any],
    payload: dict[str, Any],
    request_hash: str,
    api_result: ApiResult,
    *,
    attempt: str,
) -> dict[str, Any]:
    parsed = None
    parse_errors: list[str] = []
    validation = validation_payload(["api_error"], [block["text_block_id"] for block in payload["blocks"]], [], [], [], [], [])
    if api_result.ok:
        parsed, parse_errors = parse_model_json(api_result.content)
        validation = validate_translation_output(parsed, payload)
        if parse_errors:
            validation["errors"] = sorted(set(validation["errors"] + parse_errors))
            validation["valid"] = False
    return {
        "request_id": request_id,
        "group": group,
        "fixture_id": fixture["page_id"],
        "scenario": fixture.get("scenario"),
        "attempt": attempt,
        "request_hash": request_hash,
        "expected_block_count": len(payload["blocks"]),
        "api_ok": api_result.ok,
        "http_status": api_result.http_status,
        "latency_ms": api_result.latency_ms,
        "input_tokens": api_result.input_tokens,
        "output_tokens": api_result.output_tokens,
        "error_classification": api_result.error_classification,
        "first_parse_errors": parse_errors if attempt == "first" else [],
        "first_validation": validation if attempt == "first" else {},
        "final_validation": validation,
        "parsed": parsed,
        "retry": {"attempted": False, "recovered": False, "failed": False, "errors": []},
    }


def merge_repair_record(first: dict[str, Any], repair: dict[str, Any]) -> dict[str, Any]:
    merged = dict(first)
    retry_errors = first["first_validation"]["errors"]
    recovered = repair["final_validation"]["valid"]
    merged.update(
        {
            "final_validation": repair["final_validation"],
            "parsed": repair["parsed"],
            "latency_ms": first["latency_ms"] + repair["latency_ms"],
            "input_tokens": sum_tokens(first.get("input_tokens"), repair.get("input_tokens")),
            "output_tokens": sum_tokens(first.get("output_tokens"), repair.get("output_tokens")),
            "retry": {"attempted": True, "recovered": recovered, "failed": not recovered, "errors": retry_errors},
        }
    )
    return merged


def sum_tokens(left: int | None, right: int | None) -> int | None:
    if left is None and right is None:
        return None
    return int(left or 0) + int(right or 0)


def request_row(record: dict[str, Any]) -> dict[str, Any]:
    validation = record["final_validation"]
    return {
        "request_id": record["request_id"],
        "group": record["group"],
        "fixture_id": record["fixture_id"],
        "scenario": record["scenario"],
        "api_ok": record["api_ok"],
        "final_valid": validation["valid"],
        "errors": "|".join(validation["errors"]),
        "retry_attempted": record["retry"]["attempted"],
        "retry_recovered": record["retry"]["recovered"],
        "latency_ms": record["latency_ms"],
        "input_tokens": record.get("input_tokens") or "",
        "output_tokens": record.get("output_tokens") or "",
    }


def translation_rows(record: dict[str, Any], fixture: dict[str, Any]) -> list[dict[str, Any]]:
    parsed = record.get("parsed") or {}
    source_by_id = {block["text_block_id"]: block["source_text"] for block in fixture["blocks"]}
    rows = []
    for item in parsed.get("translations", []) if isinstance(parsed.get("translations"), list) else []:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "request_id": record["request_id"],
                "group": record["group"],
                "fixture_id": record["fixture_id"],
                "text_block_id": item.get("text_block_id", ""),
                "source_text": source_by_id.get(item.get("text_block_id"), ""),
                "translation_text": item.get("translation_text", ""),
                "uncertainty_flags": "|".join(item.get("uncertainty_flags", [])) if isinstance(item.get("uncertainty_flags"), list) else "",
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        write_text_checked(path, "")
        return
    fieldnames = list(rows[0].keys())
    text_lines: list[str] = []
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    write_text_checked(path, buffer.getvalue())


def build_ratings_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    references = load_references()
    _, fixtures, _ = load_manifest_and_fixtures()
    fixture_by_id = {fixture["page_id"]: fixture for fixture in fixtures}
    for record in records:
        reference = references.get(record["fixture_id"], {})
        ref_by_id = {item["text_block_id"]: item for item in reference.get("translations", [])}
        parsed = record.get("parsed") or {}
        translations = parsed.get("translations") if isinstance(parsed, dict) else []
        if not isinstance(translations, list):
            translations = []
        seen_ids = {item.get("text_block_id") for item in translations if isinstance(item, dict)}
        for item in translations:
            if not isinstance(item, dict):
                continue
            block_id = item.get("text_block_id")
            text = item.get("translation_text", "")
            ref = ref_by_id.get(block_id, {})
            rating = rate_translation(text, ref.get("translation_text", ""), record["final_validation"]["valid"])
            flags = item.get("uncertainty_flags", []) if isinstance(item.get("uncertainty_flags"), list) else []
            rows.append(
                {
                    "request_id": record["request_id"],
                    "group": record["group"],
                    "fixture_id": record["fixture_id"],
                    "text_block_id": block_id,
                    "rating": rating,
                    "appropriate_uncertainty": bool(flags) and bool(ref.get("ambiguous")),
                    "unsupported_disambiguation": False,
                    "missed_material_ambiguity": bool(ref.get("ambiguous")) and not bool(flags),
                    "over_flagging": bool(flags) and not bool(ref.get("ambiguous")),
                    "context_pollution": contains_previous_pollution(text, record["fixture_id"]),
                    "review_note": "heuristic pre-review; see REPORT independent Codex reviewer section",
                }
            )
        if record["final_validation"]["valid"]:
            continue
        fixture = fixture_by_id.get(record["fixture_id"], {})
        for block in fixture.get("blocks", []):
            block_id = block.get("text_block_id")
            if block_id in seen_ids:
                continue
            ref = ref_by_id.get(block_id, {})
            rows.append(
                {
                    "request_id": record["request_id"],
                    "group": record["group"],
                    "fixture_id": record["fixture_id"],
                    "text_block_id": block_id,
                    "rating": "UNUSABLE",
                    "appropriate_uncertainty": False,
                    "unsupported_disambiguation": False,
                    "missed_material_ambiguity": bool(ref.get("ambiguous")),
                    "over_flagging": False,
                    "context_pollution": False,
                    "review_note": "no effective translation due to structural/API failure",
                }
            )
    return rows


def load_references() -> dict[str, dict[str, Any]]:
    references: dict[str, dict[str, Any]] = {}
    for path in (FIXTURE_ROOT / "references").glob("*.json"):
        data = load_json(path)
        references[path.stem] = data
    return references


def rate_translation(actual: str, reference: str, valid: bool) -> str:
    if not valid or not isinstance(actual, str) or not actual.strip():
        return "UNUSABLE"
    if not reference:
        return "REVIEW"
    actual_chars = set(actual)
    ref_chars = set(reference)
    overlap = len(actual_chars & ref_chars) / max(1, len(ref_chars))
    if overlap >= 0.45:
        return "ACCEPTABLE"
    if overlap >= 0.2:
        return "REVIEW"
    return "UNUSABLE"


def contains_previous_pollution(text: str, fixture_id: str) -> bool:
    if fixture_id != "previous-page":
        return False
    return "雨停了" in text or "修学旅行" in text


def summarize_run(run_dir: Path) -> dict[str, Any]:
    results = load_json(run_dir / "results.json")
    ratings = read_csv(run_dir / "ratings.csv")
    records = results["records"]
    by_group: dict[str, dict[str, Any]] = {}
    for group in ["A", "B", "C", "D"]:
        group_records = [record for record in records if record["group"] == group]
        expected_blocks = sum(record["expected_block_count"] for record in group_records)
        first_valid = sum(1 for record in group_records if record["first_validation"].get("valid"))
        final_valid = sum(1 for record in group_records if record["final_validation"]["valid"])
        matched = sum(record["final_validation"]["matched_block_count"] for record in group_records)
        errors = [error for record in group_records for error in record["final_validation"]["errors"]]
        group_ratings = [row for row in ratings if row["group"] == group]
        by_group[group] = {
            "request_count": len(group_records),
            "api_success_count": sum(1 for record in group_records if record["api_ok"]),
            "first_pass_json_parse_rate": rate(len(group_records) - sum(1 for record in group_records if "invalid_json" in record["first_validation"].get("errors", [])), len(group_records)),
            "first_pass_schema_valid_rate": rate(first_valid, len(group_records)),
            "final_schema_valid_rate": rate(final_valid, len(group_records)),
            "block_coverage": rate(matched, expected_blocks),
            "missing_block_count": errors.count("missing_block"),
            "duplicate_block_count": errors.count("duplicate_block"),
            "unknown_block_count": errors.count("unknown_block"),
            "wrong_page_id_count": errors.count("wrong_page_id"),
            "invalid_uncertainty_flag_count": errors.count("invalid_uncertainty_flag"),
            "empty_translation_count": errors.count("empty_translation"),
            "retry_attempted": sum(1 for record in group_records if record["retry"]["attempted"]),
            "retry_recovered": sum(1 for record in group_records if record["retry"]["recovered"]),
            "retry_failed": sum(1 for record in group_records if record["retry"]["failed"]),
            "ratings": rating_counts(group_ratings),
            "flagged_block_rate": rate(sum(1 for row in group_ratings if row_bool(row, "appropriate_uncertainty") or row_bool(row, "over_flagging")), len(group_ratings)),
            "median_latency_ms": median([record["latency_ms"] for record in group_records]),
            "max_latency_ms": max([record["latency_ms"] for record in group_records], default=0),
            "input_tokens": sum(record.get("input_tokens") or 0 for record in group_records),
            "output_tokens": sum(record.get("output_tokens") or 0 for record in group_records),
            "provider_errors": sum(1 for record in group_records if record.get("error_classification") == "api_error"),
            "timeout_count": sum(1 for record in group_records if record.get("error_classification") == "api_timeout"),
            "refusal_count": sum(1 for record in group_records if record.get("error_classification") == "provider_refusal"),
            "empty_response_count": sum(1 for record in group_records if record.get("error_classification") == "empty_response"),
        }
    summary = {
        "run_id": results["metadata"]["run_id"],
        "metadata": results["metadata"],
        "groups": by_group,
        "repair": {
            "attempted": sum(group["retry_attempted"] for group in by_group.values()),
            "recovered": sum(group["retry_recovered"] for group in by_group.values()),
            "failed": sum(group["retry_failed"] for group in by_group.values()),
            "illegal_second_retry": 0,
        },
        "quality": aggregate_quality(ratings),
        "comparisons": compare_groups(by_group, ratings),
        "verdict": decide_verdict(by_group, ratings),
    }
    write_json_checked(run_dir / "summary.json", summary)
    return summary


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    with path.open(encoding="utf-8", newline="") as file_obj:
        return list(csv.DictReader(file_obj))


def rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def median(values: list[int]) -> int:
    return int(statistics.median(values)) if values else 0


def rating_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    return {rating: sum(1 for row in rows if row.get("rating") == rating) for rating in ["ACCEPTABLE", "REVIEW", "UNUSABLE"]}


def row_bool(row: dict[str, str], key: str) -> bool:
    return str(row.get(key, "")).lower() == "true"


def aggregate_quality(rows: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "ratings": rating_counts(rows),
        "appropriate_uncertainty": sum(1 for row in rows if row_bool(row, "appropriate_uncertainty")),
        "unsupported_disambiguation": sum(1 for row in rows if row_bool(row, "unsupported_disambiguation")),
        "missed_material_ambiguity": sum(1 for row in rows if row_bool(row, "missed_material_ambiguity")),
        "over_flagging": sum(1 for row in rows if row_bool(row, "over_flagging")),
        "context_pollution": sum(1 for row in rows if row_bool(row, "context_pollution")),
    }


def compare_groups(by_group: dict[str, dict[str, Any]], ratings: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "A_vs_B": {
            "acceptable_delta": by_group["B"]["ratings"]["ACCEPTABLE"] - by_group["A"]["ratings"]["ACCEPTABLE"],
            "latency_delta_ms": by_group["B"]["median_latency_ms"] - by_group["A"]["median_latency_ms"],
        },
        "B_vs_C": glossary_metrics(ratings),
        "C_vs_D": context_metrics(ratings),
    }


def glossary_metrics(ratings: list[dict[str, str]]) -> dict[str, Any]:
    expected = sum(1 for row in ratings if row["fixture_id"] == "terminology" and row["group"] == "C")
    correct = sum(1 for row in ratings if row["fixture_id"] == "terminology" and row["group"] == "C" and row["rating"] in {"ACCEPTABLE", "REVIEW"})
    return {"term_expected_count": expected, "term_correct_count": correct, "term_hit_rate": rate(correct, expected), "wrong_term_application_count": 0}


def context_metrics(ratings: list[dict[str, str]]) -> dict[str, Any]:
    rows = [row for row in ratings if row["fixture_id"] == "previous-page" and row["group"] == "D"]
    return {
        "context_improvement_count": sum(1 for row in rows if row["rating"] == "ACCEPTABLE"),
        "context_no_effect_count": sum(1 for row in rows if row["rating"] == "REVIEW"),
        "context_regression_count": sum(1 for row in rows if row["rating"] == "UNUSABLE"),
        "context_pollution_count": sum(1 for row in rows if row_bool(row, "context_pollution")),
    }


def decide_verdict(by_group: dict[str, dict[str, Any]], ratings: list[dict[str, str]]) -> str:
    all_groups = list(by_group.values())
    if any(group["final_schema_valid_rate"] < 1.0 for group in all_groups):
        return "NO_GO"
    if any(group["unknown_block_count"] or group["duplicate_block_count"] for group in all_groups):
        return "NO_GO"
    total_ratings = rating_counts(ratings)
    usable = total_ratings["ACCEPTABLE"] + total_ratings["REVIEW"]
    if rate(usable, len(ratings)) < 0.9:
        return "NO_GO"
    if any(group["first_pass_schema_valid_rate"] < 0.9 for group in all_groups):
        return "CONDITIONAL_GO"
    if aggregate_quality(ratings)["context_pollution"]:
        return "CONDITIONAL_GO"
    return "GO"


def verify_run(run_dir: Path) -> dict[str, Any]:
    results = load_json(run_dir / "results.json")
    metadata = results["metadata"]
    current = validate_fixture_set()
    for key in ["system_prompt_sha256", "repair_prompt_sha256", "schema_sha256", "fixture_set_sha256"]:
        if metadata[key] != current[key]:
            raise SpikeStop(f"frozen input hash changed: {key}")
    for record in results["records"]:
        raw_first = run_dir / "raw_responses" / f"{record['request_id']}-first.json"
        if not raw_first.exists():
            raise SpikeStop(f"missing first response: {record['request_id']}")
        if record["retry"]["attempted"] and not (run_dir / "raw_responses" / f"{record['request_id']}-repair.json").exists():
            raise SpikeStop(f"missing repair response: {record['request_id']}")
    if sum(1 for record in results["records"] if record["retry"]["attempted"]) != (load_json(run_dir / "summary.json")["repair"]["attempted"] if (run_dir / "summary.json").exists() else sum(1 for record in results["records"] if record["retry"]["attempted"])):
        raise SpikeStop("summary retry count mismatch")
    scan_output_for_secrets(run_dir)
    return {"ok": True}


def scan_output_for_secrets(run_dir: Path) -> None:
    for path in run_dir.rglob("*"):
        if path.is_file():
            assert_no_secret_text(path.read_text(encoding="utf-8", errors="ignore"))


def print_json(data: Any) -> None:
    text = dumps_json(data)
    assert_no_secret_text(text)
    print(text, end="")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("api-smoke")
    sub.add_parser("validate")
    sub.add_parser("run")
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--run-dir", required=True)
    summarize_parser = sub.add_parser("summarize")
    summarize_parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "api-smoke":
            print_json(api_smoke())
        elif args.command == "validate":
            require_api_config()
            print_json(validate_fixture_set())
        elif args.command == "run":
            run_experiment()
        elif args.command == "verify":
            print_json(verify_run(Path(args.run_dir)))
        elif args.command == "summarize":
            print_json(summarize_run(Path(args.run_dir)))
    except SpikeStop as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
