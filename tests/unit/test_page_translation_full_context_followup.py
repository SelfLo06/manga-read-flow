from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[2]
FOLLOWUP_PATH = ROOT_DIR / "tools" / "spikes" / "page_translation" / "full_context_followup.py"


def load_followup_module():
    spec = importlib.util.spec_from_file_location("page_translation_full_context_followup", FOLLOWUP_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fixture(fixture_id: str = "honorific-continuity"):
    return {
        "fixture_id": fixture_id,
        "current_page": {
            "page_id": fixture_id,
            "source_language": "ja",
            "target_language": "zh-Hans",
            "blocks": [
                {"text_block_id": f"{fixture_id}-b001", "reading_order": 1, "group_id": "g01", "source_text": "先輩、待って。"},
                {"text_block_id": f"{fixture_id}-b002", "reading_order": 2, "group_id": "g01", "source_text": "まだ話がある。"},
            ],
        },
        "glossary": [{"source": "先輩", "target": "前辈", "note": "honorific"}],
        "previous_context": [
            {"page_id": "prev", "text_block_id": "prev-b001", "translation_text": "前辈已经走了。", "status": "accepted"}
        ],
        "evaluation_focus": ["honorific_continuity"],
    }


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def make_followup_root(tmp_path: Path, module, fixtures=None):
    root = tmp_path / "full_context_followup"
    fixtures = fixtures or [fixture(f"pair-{index}") for index in range(1, 5)]
    stability_payload = {
        "page_id": "stable",
        "source_language": "ja",
        "target_language": "zh-Hans",
        "blocks": [{"text_block_id": "s-b001", "reading_order": 1, "group_id": None, "source_text": "こんにちは"}],
        "glossary": [],
        "previous_context": [],
    }
    stability_names = ["context-dependent.json", "long-page.json", "previous-page-with-context.json"]
    for name in stability_names:
        write_json(root / "stability" / name, stability_payload | {"page_id": Path(name).stem})
    pair_names = []
    for item in fixtures:
        name = item["fixture_id"] + ".json"
        pair_names.append(name)
        write_json(root / "paired" / name, item)
        write_json(
            root / "references" / f"{item['fixture_id']}.json",
            {
                "translations": [
                    {"text_block_id": block["text_block_id"], "translation_text": "参考译文"}
                    for block in item["current_page"]["blocks"]
                ]
            },
        )
    write_json(root / "manifest.json", {"stability": stability_names, "paired": pair_names})
    module.FOLLOWUP_ROOT = root
    return root


def test_np_payloads_only_differ_by_previous_context():
    followup = load_followup_module()
    item = fixture()

    assert followup.validate_np_only_differs_previous(item) is True
    result = followup.validate_pair_fixture(item)
    assert result["valid"] is True
    assert result["N"]["current_page_hash"] == result["P"]["current_page_hash"]
    assert result["N"]["glossary_hash"] == result["P"]["glossary_hash"]
    assert result["N"]["previous_context_hash"] != result["P"]["previous_context_hash"]


def test_pair_hash_validation_detects_current_page_mismatch(monkeypatch):
    followup = load_followup_module()
    item = fixture()
    original_pair_payload = followup.pair_payload

    def broken_pair_payload(fix, group):
        payload = original_pair_payload(fix, group)
        if group == "P":
            payload = json.loads(json.dumps(payload))
            payload["blocks"][0]["source_text"] = "違う"
        return payload

    monkeypatch.setattr(followup, "pair_payload", broken_pair_payload)

    result = followup.validate_pair_fixture(item)

    assert "current_page_hash_mismatch" in result["errors"]


def test_trial_count_validation_and_schedule_is_reproducible(monkeypatch, tmp_path):
    followup = load_followup_module()
    make_followup_root(tmp_path, followup)
    monkeypatch.setenv("MRF_TRANSLATION_API_BASE", "http://example.invalid/v1")
    monkeypatch.setenv("MRF_TRANSLATION_API_KEY", "test-key")
    monkeypatch.setenv("MRF_TRANSLATION_MODEL", "model")
    monkeypatch.setenv("MRF_TRANSLATION_TIMEOUT_SEC", "60")

    validation = followup.validate_followup()
    first = followup.stability_schedule()
    second = followup.stability_schedule()
    paired = followup.paired_schedule()

    assert validation["stability_payloads"] == 3
    assert len(first) == 15
    assert [trial["trial_id"] for trial in first] == [trial["trial_id"] for trial in second]
    assert len(paired) == 24


def test_http_200_empty_content_and_no_choices_classification():
    followup = load_followup_module()

    empty = followup.classify_raw_response({"choices": [{"message": {"content": "   "}, "finish_reason": "stop"}], "usage": {}})
    no_choices = followup.classify_raw_response({"choices": [], "usage": {}})
    missing_usage = followup.classify_raw_response({"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]})

    assert empty["runtime_status"] == "EMPTY_CONTENT"
    assert no_choices["runtime_status"] == "NO_CHOICES"
    assert missing_usage["runtime_status"] == "SUCCESS_RESPONSE"


def test_runtime_failure_does_not_repair(monkeypatch, tmp_path):
    followup = load_followup_module()
    make_followup_root(tmp_path, followup, [fixture("pair-1"), fixture("pair-2"), fixture("pair-3"), fixture("pair-4")])
    calls = {"repair": 0}

    def fake_call_api(config, messages, *, max_output_tokens=1200):
        return followup.runtime_payload("EMPTY_CONTENT", 1, http_status=200, raw={"choices": [{"message": {"content": ""}}]})

    def fake_repair(*args, **kwargs):
        calls["repair"] += 1
        return []

    monkeypatch.setattr(followup, "call_api", fake_call_api)
    monkeypatch.setattr(followup, "repair_messages", fake_repair)
    trial = followup.stability_schedule()[0]

    record = followup.process_trial({"base": "", "key": "", "model": "", "timeout": "60"}, trial, tmp_path / "run")

    assert record["runtime_status"] == "EMPTY_CONTENT"
    assert record["repair_attempted"] is False
    assert calls["repair"] == 0


def test_structure_error_repairs_at_most_once(monkeypatch, tmp_path):
    followup = load_followup_module()
    make_followup_root(tmp_path, followup)
    responses = [
        {
            "runtime_status": "SUCCESS_RESPONSE",
            "http_status": 200,
            "latency_ms": 1,
            "response_body_present": True,
            "choices_count": 1,
            "content_present": True,
            "content_length": 2,
            "finish_reason": "stop",
            "usage_present": False,
            "input_tokens": None,
            "output_tokens": None,
            "provider_request_id": "",
            "content": "{}",
            "raw": {},
        },
        {
            "runtime_status": "SUCCESS_RESPONSE",
            "http_status": 200,
            "latency_ms": 1,
            "response_body_present": True,
            "choices_count": 1,
            "content_present": True,
            "content_length": 2,
            "finish_reason": "stop",
            "usage_present": False,
            "input_tokens": None,
            "output_tokens": None,
            "provider_request_id": "",
            "content": "{}",
            "raw": {},
        },
    ]

    monkeypatch.setattr(followup, "call_api", lambda *args, **kwargs: responses.pop(0))
    trial = followup.stability_schedule()[0]

    record = followup.process_trial({"base": "", "key": "", "model": "", "timeout": "60"}, trial, tmp_path / "run")

    assert record["repair_attempted"] is True
    assert record["repair_failed"] is True
    assert responses == []


def test_no_output_not_counted_as_unusable_in_ratings(monkeypatch, tmp_path):
    followup = load_followup_module()
    item = fixture("pair-1")
    make_followup_root(tmp_path, followup, [item, fixture("pair-2"), fixture("pair-3"), fixture("pair-4")])
    run_dir = tmp_path / "run"
    record = {
        "experiment": "NP",
        "fixture_id": "pair-1",
        "group": "P",
        "trial_index": 1,
        "runtime_status": "EMPTY_CONTENT",
        "final_validation": {"valid": False},
    }

    followup.write_ratings(run_dir, [record])
    rows = followup.read_csv(run_dir / "ratings.csv")

    assert {row["quality_rating"] for row in rows} == {"NO_OUTPUT"}
    assert "UNUSABLE" not in {row["quality_rating"] for row in rows}


def test_schema_valid_denominator_only_successful_responses():
    followup = load_followup_module()
    records = [
        {
            "group": "N",
            "runtime_status": "SUCCESS_RESPONSE",
            "first_validation": {"valid": False, "errors": ["schema_invalid"]},
            "final_validation": {"valid": True, "errors": [], "expected_block_count": 2, "matched_block_count": 2},
            "repair_attempted": True,
            "repair_recovered": True,
            "repair_failed": False,
        },
        {
            "group": "N",
            "runtime_status": "EMPTY_CONTENT",
            "first_validation": {"valid": False, "errors": ["not_evaluable"]},
            "final_validation": {"valid": False, "errors": ["not_evaluable"], "expected_block_count": 2, "matched_block_count": 0},
            "repair_attempted": False,
            "repair_recovered": False,
            "repair_failed": False,
        },
    ]

    summary = followup.summarize_structure(records)

    assert summary["N"]["successful_response_count"] == 1
    assert summary["N"]["final_schema_valid_rate"] == 1.0


def test_end_to_end_valid_response_rate_and_mixed_outcome():
    followup = load_followup_module()
    records = [
        {
            "experiment": "S",
            "fixture_id": "stable",
            "request_hash": "h",
            "runtime_status": "SUCCESS_RESPONSE",
            "latency_ms": 1,
        },
        {
            "experiment": "S",
            "fixture_id": "stable",
            "request_hash": "h",
            "runtime_status": "EMPTY_CONTENT",
            "latency_ms": 1,
        },
        {
            "experiment": "NP",
            "group": "P",
            "runtime_status": "SUCCESS_RESPONSE",
            "latency_ms": 1,
            "input_tokens": 1,
            "output_tokens": 1,
            "final_validation": {"valid": True},
        },
        {
            "experiment": "NP",
            "group": "P",
            "runtime_status": "NO_CHOICES",
            "latency_ms": 1,
            "input_tokens": None,
            "output_tokens": None,
            "final_validation": {"valid": False},
        },
    ]

    stability = followup.summarize_stability([row for row in records if row["experiment"] == "S"])
    paired = followup.summarize_paired([row for row in records if row["experiment"] == "NP"])

    assert stability["stable"]["mixed_outcome"] is True
    assert paired["P"]["end_to_end_valid_response_rate"] == 0.5


def test_secret_redaction(monkeypatch):
    followup = load_followup_module()
    monkeypatch.setenv("MRF_TRANSLATION_API_KEY", "secret-token")

    with pytest.raises(followup.FollowupStop):
        followup.assert_no_secret_text("secret-token")
    with pytest.raises(followup.FollowupStop):
        followup.assert_no_secret_text("Authorization: Bearer nope")


def test_token_diagnostic_uses_2400_for_length_empty_candidate(monkeypatch, tmp_path):
    followup = load_followup_module()
    make_followup_root(tmp_path, followup)
    run_dir = tmp_path / "run"
    write_json(
        run_dir / "paired-results.json",
        {
            "records": [
                {
                    "trial_id": "NP-pair-1-N-01",
                    "experiment": "NP",
                    "fixture_id": "pair-1",
                    "group": "N",
                    "trial_index": 1,
                    "runtime_status": "EMPTY_CONTENT",
                    "finish_reason": "length",
                    "output_tokens": 1200,
                }
            ]
        },
    )
    monkeypatch.setenv("MRF_TRANSLATION_API_BASE", "http://example.invalid/v1")
    monkeypatch.setenv("MRF_TRANSLATION_API_KEY", "test-key")
    monkeypatch.setenv("MRF_TRANSLATION_MODEL", "model")
    monkeypatch.setenv("MRF_TRANSLATION_TIMEOUT_SEC", "60")
    seen = {}

    def fake_process_trial(config, trial, run_path, *, max_output_tokens=1200):
        seen["max_output_tokens"] = max_output_tokens
        return {
            **{key: value for key, value in trial.items() if key != "payload"},
            "runtime_status": "SUCCESS_RESPONSE",
            "final_validation": {"valid": True},
        }

    monkeypatch.setattr(followup, "process_trial", fake_process_trial)

    result = followup.run_token_diagnostic(run_dir)

    assert result["executed"] is True
    assert seen["max_output_tokens"] == 2400
    assert result["record"]["experiment"] == "TOKEN_DIAGNOSTIC"
