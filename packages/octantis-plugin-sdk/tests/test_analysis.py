# SPDX-License-Identifier: Apache-2.0
"""Severity and ActionPlan tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from octantis_plugin_sdk import (
    ActionPlan,
    ActionStep,
    Severity,
    SeverityAnalysis,
    StepType,
)


def test_severity_should_notify():
    assert Severity.CRITICAL.should_notify
    assert Severity.MODERATE.should_notify
    assert not Severity.LOW.should_notify
    assert not Severity.NOT_A_PROBLEM.should_notify


def test_severity_colors_and_emoji():
    assert Severity.CRITICAL.color_hex == "#FF0000"
    assert Severity.CRITICAL.discord_color == 0xFF0000
    assert Severity.CRITICAL.emoji == ":red_circle:"


def test_severity_values_enumerate_exactly_four():
    assert {s.value for s in Severity} == {
        "CRITICAL", "MODERATE", "LOW", "NOT_A_PROBLEM",
    }


def test_severity_analysis_confidence_bounds():
    SeverityAnalysis(severity=Severity.LOW, confidence=0.0, reasoning="x")
    SeverityAnalysis(severity=Severity.LOW, confidence=1.0, reasoning="x")
    with pytest.raises(ValidationError):
        SeverityAnalysis(severity=Severity.LOW, confidence=1.1, reasoning="x")
    with pytest.raises(ValidationError):
        SeverityAnalysis(severity=Severity.LOW, confidence=-0.1, reasoning="x")


def test_action_step_required_fields():
    ActionStep(order=1, type=StepType.INVESTIGATE, title="t", description="d")
    with pytest.raises(ValidationError):
        ActionStep(order=1, type=StepType.INVESTIGATE, title="t")  # type: ignore[call-arg]


def test_action_plan_steps_markdown():
    plan = ActionPlan(
        title="Rollback",
        summary="s",
        steps=[
            ActionStep(order=1, type=StepType.ROLLBACK, title="revert",
                       description="undo", command="kubectl rollout undo",
                       expected_outcome="pods recover"),
        ],
    )
    md = plan.steps_markdown
    assert "[ROLLBACK] revert" in md
    assert "kubectl rollout undo" in md
    assert "_Expected: pods recover_" in md


def test_step_type_values():
    assert {t.value for t in StepType} == {
        "investigate", "execute", "escalate", "monitor", "rollback",
    }
