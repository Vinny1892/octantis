"""Unit tests for graph/nodes/utils.py — JSON parsing, language, model helpers."""

import json
from unittest.mock import patch

import pytest

from octantis.graph.nodes.utils import (
    _repair_truncated_json,
    get_litellm_model,
    get_llm_api_key,
    language_instruction,
    parse_llm_json,
)

# ─── parse_llm_json ────────────────────────────────────────────────────────


def test_parse_valid_json():
    raw = '{"severity": "CRITICAL", "confidence": 0.9}'
    result = parse_llm_json(raw)
    assert result["severity"] == "CRITICAL"
    assert result["confidence"] == 0.9


def test_parse_json_with_fences():
    raw = '```json\n{"severity": "LOW"}\n```'
    result = parse_llm_json(raw)
    assert result["severity"] == "LOW"


def test_parse_json_with_unclosed_fence():
    raw = '```json\n{"severity": "MODERATE"}'
    result = parse_llm_json(raw)
    assert result["severity"] == "MODERATE"


def test_parse_json_invalid_raises():
    with pytest.raises(json.JSONDecodeError):
        parse_llm_json("not json at all")


def test_parse_json_empty_fence():
    raw = "```json\n\n```"
    with pytest.raises(json.JSONDecodeError):
        parse_llm_json(raw)


# ─── _repair_truncated_json ────────────────────────────────────────────────


def test_repair_truncated_object():
    raw = '{"severity": "CRITICAL", "confidence": 0.9'
    result = _repair_truncated_json(raw)
    assert result["severity"] == "CRITICAL"


def test_repair_truncated_array():
    raw = '{"steps": [{"order": 1}'
    result = _repair_truncated_json(raw)
    assert result["steps"][0]["order"] == 1


def test_repair_truncated_with_trailing_comma():
    raw = '{"a": 1, "b": 2,'
    result = _repair_truncated_json(raw)
    assert result["a"] == 1
    assert result["b"] == 2


def test_repair_truncated_with_partial_key():
    raw = '{"a": 1, "b":'
    result = _repair_truncated_json(raw)
    assert result["a"] == 1
    assert result["b"] is None


def test_repair_not_truncated_raises():
    with pytest.raises(json.JSONDecodeError):
        _repair_truncated_json('{"a": 1}')


def test_repair_truncated_string():
    raw = '{"msg": "hello wor'
    result = _repair_truncated_json(raw)
    assert "hello wor" in result["msg"]


# ─── language_instruction ──────────────────────────────────────────────────


def test_language_instruction_english():
    result = language_instruction("en")
    assert "English" in result
    assert "JSON keys must remain in English" in result


def test_language_instruction_ptbr():
    result = language_instruction("pt-br")
    assert "Brazilian Portuguese" in result


def test_language_instruction_unknown_defaults_to_english():
    result = language_instruction("xx")
    assert "English" in result


# ─── get_litellm_model ─────────────────────────────────────────────────────


def test_get_litellm_model_anthropic():
    assert get_litellm_model("anthropic", "claude-sonnet-4-6") == "claude-sonnet-4-6"


def test_get_litellm_model_openrouter():
    assert get_litellm_model("openrouter", "claude-sonnet-4-6") == "openrouter/claude-sonnet-4-6"


def test_get_litellm_model_bedrock():
    assert (
        get_litellm_model("bedrock", "global.anthropic.claude-opus-4-6-v1")
        == "bedrock/global.anthropic.claude-opus-4-6-v1"
    )


# ─── get_llm_api_key ──────────────────────────────────────────────────────


def test_get_llm_api_key_anthropic():
    with patch("octantis.config.settings") as mock:
        mock.llm.anthropic_api_key = "sk-ant-test"
        assert get_llm_api_key("anthropic") == "sk-ant-test"


def test_get_llm_api_key_openrouter():
    with patch("octantis.config.settings") as mock:
        mock.llm.openrouter_api_key = "sk-or-test"
        assert get_llm_api_key("openrouter") == "sk-or-test"


def test_get_llm_api_key_bedrock_returns_none():
    assert get_llm_api_key("bedrock") is None
