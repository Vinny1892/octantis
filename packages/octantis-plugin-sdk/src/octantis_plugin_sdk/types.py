# SPDX-License-Identifier: Apache-2.0
"""Shared data types exchanged across plugin boundaries.

These types are the stable contract between Octantis core and plugin authors.
They are intentionally minimal: additions require a minor SDK bump, removals
or signature changes require a major bump.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PluginTier(str, Enum):
    """Minimum license tier at which a plugin is permitted to load."""

    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class PluginMetadata(BaseModel):
    """Optional structured metadata a plugin may expose via a `metadata` attribute.

    The registry may surface these fields in logs and metrics but does not
    require the plugin to provide them.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    tier: PluginTier = PluginTier.FREE
    description: str | None = None
    homepage: str | None = None


class Tool(BaseModel):
    """An MCP tool exposed by an `MCPConnector` to the investigation runtime."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str
    description: str
    datasource: str
    invoke: Any
    input_schema: dict[str, Any] = Field(default_factory=dict)


class Event(BaseModel):
    """Canonical event shape consumed by Processors, MCPConnectors, and Notifiers.

    Mirrors the core `InfraEvent` fields that plugins are allowed to rely on.
    Runtime-only fields (queue offsets, consumer metadata) stay in the core
    and do not cross the SDK boundary.
    """

    model_config = ConfigDict(frozen=False)

    event_id: str
    event_type: str
    source: str
    resource: dict[str, Any] = Field(default_factory=dict)
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    logs: list[dict[str, Any]] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InvestigationResult(BaseModel):
    """Output of an investigation workflow passed to Notifier plugins."""

    model_config = ConfigDict(frozen=False)

    event_id: str
    original_event: Event
    evidence_summary: str = ""
    mcp_servers_used: list[str] = Field(default_factory=list)
    mcp_degraded: bool = False
    budget_exhausted: bool = False
    investigation_duration_s: float = 0.0
    tokens_input: int = 0
    tokens_output: int = 0
    extra: dict[str, Any] = Field(default_factory=dict)
