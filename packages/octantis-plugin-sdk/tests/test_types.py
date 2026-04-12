# SPDX-License-Identifier: Apache-2.0
"""Shared type tests — immutability and minimal contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from octantis_plugin_sdk import (
    Event,
    InvestigationResult,
    PluginMetadata,
    PluginTier,
    Tool,
)


def test_plugin_metadata_frozen():
    md = PluginMetadata(name="x", version="0.1.0")
    with pytest.raises(ValidationError):
        md.name = "y"


def test_plugin_tier_default_free():
    md = PluginMetadata(name="x", version="0.1.0")
    assert md.tier is PluginTier.FREE


def test_tool_frozen():
    t = Tool(name="t", description="d", datasource="promql", invoke=lambda: None)
    with pytest.raises(ValidationError):
        t.name = "other"


def test_event_required_fields():
    e = Event(event_id="e1", event_type="metric", source="test")
    assert e.event_id == "e1"
    assert e.received_at is not None


def test_event_missing_required_field():
    with pytest.raises(ValidationError):
        Event(event_type="metric", source="test")  # type: ignore[call-arg]


def test_investigation_result_roundtrip():
    evt = Event(event_id="e1", event_type="metric", source="s")
    res = InvestigationResult(event_id="e1", original_event=evt)
    assert res.event_id == "e1"
    assert res.original_event.event_id == "e1"
    assert res.mcp_degraded is False


def test_plugin_tier_values():
    assert {t.value for t in PluginTier} == {"free", "pro", "enterprise"}
