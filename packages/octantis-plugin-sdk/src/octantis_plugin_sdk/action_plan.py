# SPDX-License-Identifier: Apache-2.0
"""Shared action plan types — remediation plan produced by the planner node."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class StepType(str, Enum):
    INVESTIGATE = "investigate"
    EXECUTE = "execute"
    ESCALATE = "escalate"
    MONITOR = "monitor"
    ROLLBACK = "rollback"


class ActionStep(BaseModel):
    model_config = ConfigDict(frozen=False)

    order: int
    type: StepType
    title: str
    description: str
    command: str | None = None
    expected_outcome: str | None = None
    risk: str | None = None


class ActionPlan(BaseModel):
    model_config = ConfigDict(frozen=False)

    title: str
    summary: str
    steps: list[ActionStep]
    escalate_to: list[str] = Field(default_factory=list)
    estimated_resolution_minutes: int | None = None
    runbook_url: str | None = None
    grafana_dashboard_url: str | None = None

    @property
    def steps_markdown(self) -> str:
        lines: list[str] = []
        for step in self.steps:
            lines.append(f"**{step.order}. [{step.type.value.upper()}] {step.title}**")
            lines.append(step.description)
            if step.command:
                lines.append(f"```\n{step.command}\n```")
            if step.expected_outcome:
                lines.append(f"_Expected: {step.expected_outcome}_")
        return "\n".join(lines)
