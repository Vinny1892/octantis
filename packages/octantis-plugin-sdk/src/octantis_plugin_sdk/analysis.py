# SPDX-License-Identifier: Apache-2.0
"""Shared analysis types — LLM output passed to Notifier plugins.

`Severity` is the canonical scale used by the severity classifier node and
consumed by notifiers. `SeverityAnalysis` is the full classification record.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    MODERATE = "MODERATE"
    LOW = "LOW"
    NOT_A_PROBLEM = "NOT_A_PROBLEM"

    @property
    def should_notify(self) -> bool:
        return self in (Severity.CRITICAL, Severity.MODERATE)

    @property
    def color_hex(self) -> str:
        return {
            Severity.CRITICAL: "#FF0000",
            Severity.MODERATE: "#FFA500",
            Severity.LOW: "#FFFF00",
            Severity.NOT_A_PROBLEM: "#00FF00",
        }[self]

    @property
    def discord_color(self) -> int:
        return int(self.color_hex.lstrip("#"), 16)

    @property
    def emoji(self) -> str:
        return {
            Severity.CRITICAL: ":red_circle:",
            Severity.MODERATE: ":large_orange_circle:",
            Severity.LOW: ":yellow_circle:",
            Severity.NOT_A_PROBLEM: ":white_check_mark:",
        }[self]


class SeverityAnalysis(BaseModel):
    """LLM classification output."""

    model_config = ConfigDict(frozen=False)

    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    affected_components: list[str] = Field(default_factory=list)
    is_transient: bool = False
    similar_past_issues: list[str] = Field(default_factory=list)
