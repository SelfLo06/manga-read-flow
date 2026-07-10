from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[2]
SPIKE_PATH = ROOT_DIR / "tools" / "spikes" / "page_translation" / "spike.py"


def load_spike_module():
    spec = importlib.util.spec_from_file_location("page_translation_spike", SPIKE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fixture(blocks=None, page_id="p1"):
    return {
        "page_id": page_id,
        "scenario": "basic-dialogue",
        "source_language": "ja",
        "target_language": "zh-Hans",
        "blocks": blocks
        or [
            {"text_block_id": "b1", "reading_order": 1, "group_id": None, "source_text": "こんにちは"},
            {"text_block_id": "b2", "reading_order": 2, "group_id": None, "source_text": "またね"},
        ],
        "glossary": [],
        "previous_context": [],
    }


def valid_result(page_id="p1"):
    return {
        "page_id": page_id,
        "translations": [
            {"text_block_id": "b1", "translation_text": "你好", "uncertainty_flags": []},
            {"text_block_id": "b2", "translation_text": "再见", "uncertainty_flags": []},
        ],
    }


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def write_fixture_root(tmp_path: Path, fixtures: list[dict], references: dict[str, dict] | None = None) -> Path:
    root = tmp_path / "page_translation"
    write_json(
        root / "schema.json",
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {},
            "required": ["page_id", "translations"],
        },
    )
    names = []
    for item in fixtures:
        name = item["page_id"] + ".json"
        names.append(name)
        write_json(root / "fixtures" / name, item)
    write_json(root / "manifest.json", {"fixtures": names, "required_scenarios": []})
    for page_id, ref in (references or {}).items():
        write_json(root / "references" / f"{page_id}.json", ref)
    return root


def test_prompt_load_and_hash():
    spike = load_spike_module()

    assert spike.PROMPT_PATH.read_text(encoding="utf-8").strip()
    assert len(spike.sha256_file(spike.PROMPT_PATH)) == 64


def test_manifest_and_fixture_validation_passes(monkeypatch, tmp_path):
    spike = load_spike_module()
    root = write_fixture_root(tmp_path, [fixture()])

    result = spike.validate_fixture_set(root)

    assert result["ok"] is True
    assert result["page_count"] == 1
    assert result["block_count"] == 2


def test_duplicate_page_id_fails(tmp_path):
    spike = load_spike_module()
    root = tmp_path / "page_translation"
    write_json(root / "schema.json", {"type": "object", "additionalProperties": False})
    write_json(root / "manifest.json", {"fixtures": ["a.json", "b.json"]})
    write_json(root / "fixtures" / "a.json", fixture(page_id="dup"))
    write_json(root / "fixtures" / "b.json", fixture(page_id="dup"))

    with pytest.raises(spike.SpikeStop, match="duplicate_page_id"):
        spike.validate_fixture_set(root)


def test_duplicate_block_id_fails(tmp_path):
    spike = load_spike_module()
    item = fixture(blocks=[
        {"text_block_id": "b1", "reading_order": 1, "group_id": None, "source_text": "A"},
        {"text_block_id": "b1", "reading_order": 2, "group_id": None, "source_text": "B"},
    ])
    root = write_fixture_root(tmp_path, [item])

    with pytest.raises(spike.SpikeStop, match="duplicate_block_id"):
        spike.validate_fixture_set(root)


def test_reading_order_conflict_fails(tmp_path):
    spike = load_spike_module()
    item = fixture(blocks=[
        {"text_block_id": "b1", "reading_order": 1, "group_id": None, "source_text": "A"},
        {"text_block_id": "b2", "reading_order": 1, "group_id": None, "source_text": "B"},
    ])
    root = write_fixture_root(tmp_path, [item])

    with pytest.raises(spike.SpikeStop, match="duplicate_reading_order"):
        spike.validate_fixture_set(root)


def test_valid_json_validation():
    spike = load_spike_module()

    parsed, parse_errors = spike.parse_model_json(json.dumps(valid_result(), ensure_ascii=False))
    validation = spike.validate_translation_output(parsed, fixture())

    assert parse_errors == []
    assert validation["valid"] is True


def test_markdown_wrapped_json_is_detected_but_parseable():
    spike = load_spike_module()

    parsed, parse_errors = spike.parse_model_json("```json\n" + json.dumps(valid_result(), ensure_ascii=False) + "\n```")

    assert parsed["page_id"] == "p1"
    assert parse_errors == ["markdown_wrapped_json"]


def test_invalid_json_is_classified():
    spike = load_spike_module()

    parsed, errors = spike.parse_model_json("{not json")

    assert parsed is None
    assert errors == ["invalid_json"]


def test_wrong_page_id_is_invalid():
    spike = load_spike_module()

    validation = spike.validate_translation_output(valid_result(page_id="wrong"), fixture())

    assert "wrong_page_id" in validation["errors"]


def test_missing_duplicate_and_unknown_blocks_are_invalid():
    spike = load_spike_module()
    result = {
        "page_id": "p1",
        "translations": [
            {"text_block_id": "b1", "translation_text": "你好", "uncertainty_flags": []},
            {"text_block_id": "b1", "translation_text": "你好", "uncertainty_flags": []},
            {"text_block_id": "b3", "translation_text": "未知", "uncertainty_flags": []},
        ],
    }

    validation = spike.validate_translation_output(result, fixture())

    assert {"missing_block", "duplicate_block", "unknown_block"}.issubset(set(validation["errors"]))


def test_invalid_uncertainty_flag_is_invalid():
    spike = load_spike_module()
    result = valid_result()
    result["translations"][0]["uncertainty_flags"] = ["made_up_flag"]

    validation = spike.validate_translation_output(result, fixture())

    assert "invalid_uncertainty_flag" in validation["errors"]


def test_empty_translation_is_invalid_but_not_retryable():
    spike = load_spike_module()
    result = valid_result()
    result["translations"][0]["translation_text"] = ""

    validation = spike.validate_translation_output(result, fixture())

    assert "empty_translation" in validation["errors"]
    assert spike.should_attempt_repair(True, None, validation["errors"]) is False


def test_previous_context_bound_fails(tmp_path):
    spike = load_spike_module()
    item = fixture()
    item["previous_context"] = [
        {"page_id": f"prev-{index}", "text_block_id": f"pb{index}", "translation_text": "x", "status": "accepted"}
        for index in range(21)
    ]
    root = write_fixture_root(tmp_path, [item])

    with pytest.raises(spike.SpikeStop, match="previous_context_bound"):
        spike.validate_fixture_set(root)


def test_reference_leakage_fails(tmp_path):
    spike = load_spike_module()
    item = fixture()
    item["blocks"][0]["source_text"] = "参考译文"
    root = write_fixture_root(
        tmp_path,
        [item],
        {"p1": {"translations": [{"text_block_id": "b1", "translation_text": "参考译文"}]}},
    )

    with pytest.raises(spike.SpikeStop, match="reference_leakage"):
        spike.validate_fixture_set(root)


def test_retry_max_once_and_refusal_no_repair():
    spike = load_spike_module()

    assert spike.should_attempt_repair(True, None, ["missing_block"]) is True
    assert spike.should_attempt_repair(False, "provider_refusal", ["missing_block"]) is False
    first = {"first_validation": {"errors": ["missing_block"]}, "latency_ms": 1, "input_tokens": 2, "output_tokens": 3}
    repair = {
        "final_validation": {"valid": True},
        "parsed": valid_result(),
        "latency_ms": 4,
        "input_tokens": 5,
        "output_tokens": 6,
    }

    merged = spike.merge_repair_record(first, repair)

    assert merged["retry"] == {"attempted": True, "recovered": True, "failed": False, "errors": ["missing_block"]}


def test_log_redaction(monkeypatch):
    spike = load_spike_module()
    monkeypatch.setenv("MRF_TRANSLATION_API_KEY", "secret-value")

    with pytest.raises(spike.SpikeStop):
        spike.assert_no_secret_text("contains secret-value")
    with pytest.raises(spike.SpikeStop):
        spike.assert_no_secret_text("Authorization: Bearer x")


def test_summary_consistency(tmp_path):
    spike = load_spike_module()
    run_dir = tmp_path / "run"
    record = {
        "request_id": "B-p1-01",
        "group": "B",
        "fixture_id": "p1",
        "scenario": "basic-dialogue",
        "expected_block_count": 2,
        "api_ok": True,
        "latency_ms": 10,
        "input_tokens": 20,
        "output_tokens": 5,
        "error_classification": None,
        "first_validation": {"valid": True, "errors": [], "matched_block_count": 2},
        "final_validation": {"valid": True, "errors": [], "matched_block_count": 2},
        "retry": {"attempted": False, "recovered": False, "failed": False, "errors": []},
        "parsed": valid_result(),
    }
    write_json(run_dir / "results.json", {"metadata": {"run_id": "r1"}, "records": [record]})
    (run_dir / "ratings.csv").write_text(
        "request_id,group,fixture_id,text_block_id,rating,appropriate_uncertainty,unsupported_disambiguation,missed_material_ambiguity,over_flagging,context_pollution,review_note\n"
        "B-p1-01,B,p1,b1,ACCEPTABLE,False,False,False,False,False,\n"
        "B-p1-01,B,p1,b2,REVIEW,False,False,False,False,False,\n",
        encoding="utf-8",
    )

    summary = spike.summarize_run(run_dir)

    assert summary["groups"]["B"]["request_count"] == 1
    assert summary["groups"]["B"]["final_schema_valid_rate"] == 1.0
    assert summary["repair"]["attempted"] == 0


def test_failed_request_adds_unusable_rating(monkeypatch):
    spike = load_spike_module()
    record = {
        "request_id": "D-p1-01",
        "group": "D",
        "fixture_id": "p1",
        "final_validation": {"valid": False},
        "parsed": None,
    }
    fixture_item = fixture()
    monkeypatch.setattr(spike, "load_manifest_and_fixtures", lambda: ({}, [fixture_item], [Path("p1.json")]))
    monkeypatch.setattr(
        spike,
        "load_references",
        lambda: {
            "p1": {
                "translations": [
                    {"text_block_id": "b1", "translation_text": "你好", "ambiguous": False},
                    {"text_block_id": "b2", "translation_text": "再见", "ambiguous": True},
                ]
            }
        },
    )

    rows = spike.build_ratings_rows([record])

    assert [row["rating"] for row in rows] == ["UNUSABLE", "UNUSABLE"]
    assert rows[1]["missed_material_ambiguity"] is True
