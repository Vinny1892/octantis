"""Unit tests for action_plan model — steps_markdown property."""

from octantis.models.action_plan import ActionPlan, ActionStep, StepType


def test_steps_markdown_basic():
    plan = ActionPlan(
        title="Fix OOM",
        summary="Increase memory",
        steps=[
            ActionStep(
                order=1,
                type=StepType.INVESTIGATE,
                title="Check memory",
                description="Review container memory metrics",
            ),
        ],
    )
    md = plan.steps_markdown
    assert "**1. [INVESTIGATE] Check memory**" in md
    assert "Review container memory metrics" in md


def test_steps_markdown_with_command():
    plan = ActionPlan(
        title="Fix",
        summary="Fix it",
        steps=[
            ActionStep(
                order=1,
                type=StepType.EXECUTE,
                title="Scale up",
                description="Increase replicas",
                command="kubectl scale deployment/api --replicas=3",
            ),
        ],
    )
    md = plan.steps_markdown
    assert "```" in md
    assert "kubectl scale" in md


def test_steps_markdown_with_expected_outcome():
    plan = ActionPlan(
        title="Fix",
        summary="Fix it",
        steps=[
            ActionStep(
                order=1,
                type=StepType.MONITOR,
                title="Watch metrics",
                description="Monitor CPU after fix",
                expected_outcome="CPU drops below 80%",
            ),
        ],
    )
    md = plan.steps_markdown
    assert "_Expected: CPU drops below 80%_" in md


def test_steps_markdown_multiple_steps():
    plan = ActionPlan(
        title="Multi-step fix",
        summary="Several actions",
        steps=[
            ActionStep(
                order=1,
                type=StepType.INVESTIGATE,
                title="Diagnose",
                description="Check logs",
            ),
            ActionStep(
                order=2,
                type=StepType.EXECUTE,
                title="Fix",
                description="Apply patch",
                command="kubectl apply -f fix.yaml",
            ),
            ActionStep(
                order=3,
                type=StepType.ESCALATE,
                title="Notify team",
                description="Alert SRE team",
            ),
        ],
    )
    md = plan.steps_markdown
    assert "[INVESTIGATE]" in md
    assert "[EXECUTE]" in md
    assert "[ESCALATE]" in md
    assert "kubectl apply" in md


def test_steps_markdown_all_step_types():
    for step_type in StepType:
        plan = ActionPlan(
            title="Test",
            summary="Test",
            steps=[
                ActionStep(
                    order=1,
                    type=step_type,
                    title="Step",
                    description="Desc",
                ),
            ],
        )
        md = plan.steps_markdown
        assert f"[{step_type.value.upper()}]" in md
