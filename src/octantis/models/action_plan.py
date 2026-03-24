"""Action plan model produced by the planner LLM node."""

from enum import Enum

from pydantic import BaseModel, Field


class StepType(str, Enum):
    INVESTIGATE = "investigate"
    EXECUTE = "execute"
    ESCALATE = "escalate"
    MONITOR = "monitor"
    ROLLBACK = "rollback"


class ActionStep(BaseModel):
    """A single remediation step."""

    order: int
    type: StepType
    title: str
    description: str
    command: str | None = Field(
        default=None,
        description="kubectl / helm / shell command to run",
    )
    expected_outcome: str | None = None
    risk: str | None = Field(
        default=None,
        description="Risk or side-effects of this step",
    )


class ActionPlan(BaseModel):
    """Structured remediation plan produced by the LLM."""

    title: str
    summary: str
    steps: list[ActionStep]
    escalate_to: list[str] = Field(
        default_factory=list,
        description="Teams or individuals to escalate to if plan fails",
    )
    estimated_resolution_minutes: int | None = None
    runbook_url: str | None = None
    grafana_dashboard_url: str | None = None

    @property
    def steps_markdown(self) -> str:
        lines = []
        for step in self.steps:
            lines.append(f"**{step.order}. [{step.type.value.upper()}] {step.title}**")
            lines.append(step.description)
            if step.command:
                lines.append(f"```\n{step.command}\n```")
            if step.expected_outcome:
                lines.append(f"_Expected: {step.expected_outcome}_")
        return "\n".join(lines)
