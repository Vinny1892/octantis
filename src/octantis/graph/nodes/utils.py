"""Shared utilities for graph nodes."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)


def parse_llm_json(raw: str) -> Any:
    """Parse JSON from an LLM response, stripping markdown fences if present."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try extracting from ```json ... ``` fences
    match = _FENCED_JSON_RE.search(raw)
    if match:
        return json.loads(match.group(1).strip())

    raise json.JSONDecodeError("No valid JSON found", raw, 0)
