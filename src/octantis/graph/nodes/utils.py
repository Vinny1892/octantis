# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared utilities for graph nodes."""

from __future__ import annotations

import json
import re
from typing import Any

# Matches ```json ... ``` (closing fence optional for truncated responses)
_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*\n?(.*?)(?:```|$)", re.DOTALL)


def _repair_truncated_json(raw: str) -> Any:
    """Try to repair truncated JSON by closing open brackets/braces."""
    # Count open/close brackets
    opens = []
    in_string = False
    escape = False
    for ch in raw:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ("{", "["):
            opens.append(ch)
        elif (ch == "}" and opens and opens[-1] == "{") or (
            ch == "]" and opens and opens[-1] == "["
        ):
            opens.pop()

    if not opens:
        raise json.JSONDecodeError("Not truncated", raw, 0)

    # Close everything that's open, trimming any trailing partial value
    repaired = raw.rstrip()

    # If we're inside an unclosed string, close it first
    if in_string:
        repaired += '"'

    # Remove trailing comma or partial key/value
    repaired = re.sub(r",\s*$", "", repaired)
    repaired = re.sub(r":\s*$", ": null", repaired)

    for bracket in reversed(opens):
        repaired += "]" if bracket == "[" else "}"

    return json.loads(repaired)


def parse_llm_json(raw: str) -> Any:
    """Parse JSON from an LLM response, stripping markdown fences if present."""
    # 1. Try raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 2. Try extracting from ```json ... ``` fences
    content = raw
    match = _FENCED_JSON_RE.search(raw)
    if match:
        extracted = match.group(1).strip()
        if extracted:
            content = extracted
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                pass

    # 3. Try repairing truncated JSON
    try:
        return _repair_truncated_json(content)
    except (json.JSONDecodeError, Exception):
        pass

    raise json.JSONDecodeError("No valid JSON found", raw, 0)


_LANGUAGE_LABELS = {
    "en": "English",
    "pt-br": "Brazilian Portuguese (pt-BR)",
}


def language_instruction(lang: str) -> str:
    """Return a prompt instruction line for the configured language."""
    label = _LANGUAGE_LABELS.get(lang, _LANGUAGE_LABELS["en"])
    return f"\nIMPORTANT: Write ALL free-text fields (reasoning, summary, descriptions, titles) in {label}. JSON keys must remain in English."


def get_litellm_model(provider: str, model: str) -> str:
    """Return the litellm model string for the given provider."""
    if provider == "openrouter":
        return f"openrouter/{model}"
    if provider == "bedrock":
        return f"bedrock/{model}"
    return model


def get_llm_api_key(provider: str) -> str | None:
    """Return the API key for the provider, or None for Bedrock (uses AWS credential chain)."""
    from octantis.config import settings

    if provider == "anthropic":
        return settings.llm.anthropic_api_key
    if provider == "openrouter":
        return settings.llm.openrouter_api_key
    # Bedrock: boto3 handles auth via AWS credential chain
    return None
