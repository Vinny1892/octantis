"""Planner node: uses LLM to generate a concrete remediation action plan."""

import structlog
from litellm import acompletion

from octantis.config import settings
from octantis.graph.nodes.utils import (
    get_litellm_model,
    get_llm_api_key,
    language_instruction,
    parse_llm_json,
)
from octantis.graph.state import AgentState
from octantis.models.action_plan import ActionPlan, ActionStep, StepType

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = """\
You are Octantis, an expert SRE with deep Kubernetes/EKS knowledge.
Given an infrastructure incident analysis, generate a concrete, prioritized remediation plan.

Steps should be:
1. Immediately actionable (real kubectl/helm/shell commands where applicable)
2. Ordered by priority (most critical first)
3. Include expected outcomes and risks

Respond ONLY with a valid JSON object matching this schema:
{
  "title": "short incident title",
  "summary": "1-2 sentence summary of the issue and approach",
  "steps": [
    {
      "order": 1,
      "type": "investigate|execute|escalate|monitor|rollback",
      "title": "step title",
      "description": "what to do and why",
      "command": "kubectl get pods -n namespace | optional shell command",
      "expected_outcome": "what success looks like",
      "risk": "any risk or side effect"
    }
  ],
  "escalate_to": ["team-sre", "team-platform"],
  "estimated_resolution_minutes": 30,
  "runbook_url": null,
  "grafana_dashboard_url": null
}
"""


def _build_user_message(state: AgentState) -> str:
    investigation = state["investigation"]
    analysis = state["analysis"]
    event = investigation.original_event

    return f"""Generate a remediation plan for this incident:

Severity: {analysis.severity} (confidence: {analysis.confidence:.0%})
Analysis: {analysis.reasoning}
Affected components: {", ".join(analysis.affected_components) or "unknown"}
Is transient: {analysis.is_transient}

Investigation summary:
{investigation.evidence_summary[:1000]}

Kubernetes namespace: {event.resource.k8s_namespace or "unknown"}
Pod: {event.resource.k8s_pod_name or "unknown"}
Node: {event.resource.k8s_node_name or "unknown"}
Deployment: {event.resource.k8s_deployment_name or "unknown"}
"""


async def planner_node(state: AgentState) -> AgentState:
    """Call LLM to generate remediation action plan."""
    event_id = state["investigation"].original_event.event_id
    log.info("planner.start", event_id=event_id, severity=state["analysis"].severity)

    model = get_litellm_model(settings.llm.provider, settings.llm.model)
    api_key = get_llm_api_key(settings.llm.provider)

    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT + language_instruction(settings.language)},
            {"role": "user", "content": _build_user_message(state)},
        ],
        "max_tokens": settings.llm.max_tokens,
        "temperature": settings.llm.temperature,
        "response_format": {"type": "json_object"},
    }
    if api_key:
        kwargs["api_key"] = api_key

    response = await acompletion(**kwargs)

    usage = response.get("usage", {})
    input_tokens = getattr(usage, "prompt_tokens", 0)
    output_tokens = getattr(usage, "completion_tokens", 0)

    from octantis.metrics import LLM_TOKENS_INPUT, LLM_TOKENS_OUTPUT, LLM_TOKENS_TOTAL

    LLM_TOKENS_INPUT.labels(node="plan").inc(input_tokens)
    LLM_TOKENS_OUTPUT.labels(node="plan").inc(output_tokens)
    LLM_TOKENS_TOTAL.labels(node="plan").inc(input_tokens + output_tokens)

    raw_content = response.choices[0].message.content
    try:
        data = parse_llm_json(raw_content)
        # Coerce step types safely
        for step in data.get("steps", []):
            if "type" in step and step["type"] not in StepType._value2member_map_:
                step["type"] = StepType.INVESTIGATE.value
        plan = ActionPlan(**data)
    except Exception as exc:
        log.error("planner.parse_error", error=str(exc), raw=raw_content[:300])
        plan = ActionPlan(
            title="Remediation plan (parse error)",
            summary="LLM response could not be parsed. Review raw data manually.",
            steps=[
                ActionStep(
                    order=1,
                    type=StepType.INVESTIGATE,
                    title="Manual investigation required",
                    description=f"Could not parse LLM plan. Raw response: {raw_content[:500]}",
                )
            ],
        )

    log.info("planner.done", event_id=event_id, steps=len(plan.steps))
    return {**state, "action_plan": plan}
