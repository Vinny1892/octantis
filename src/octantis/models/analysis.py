"""LLM severity analysis model."""

from enum import Enum

from pydantic import BaseModel, Field


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
        """Discord embed color as integer."""
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
    """LLM output: classification of an infrastructure event."""

    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0, description="0.0 to 1.0")
    reasoning: str = Field(description="LLM explanation for the classification")
    affected_components: list[str] = Field(
        default_factory=list,
        description="Services/pods/nodes affected",
    )
    is_transient: bool = Field(
        default=False,
        description="True if the issue is likely temporary/self-resolving",
    )
    similar_past_issues: list[str] = Field(
        default_factory=list,
        description="Known patterns this resembles",
    )
