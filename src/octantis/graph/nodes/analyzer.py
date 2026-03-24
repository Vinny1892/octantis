"""Analyzer node: uses LLM to classify severity of an infrastructure event."""

import json

import structlog
from litellm import acompletion

from octantis.config import settings
from octantis.graph.state import AgentState
from octantis.models.analysis import Severity, SeverityAnalysis

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = """\
You are Octantis, an expert SRE/infrastructure analyst.
Your job is to assess infrastructure events from a Kubernetes/EKS environment and
classify their real severity — going beyond simple threshold breaches.

You will receive enriched telemetry data (metrics, logs, K8s state, Prometheus context)
and must determine the TRUE operational impact.

Severity levels:
- CRITICAL: Requires immediate action. Service is down or severely degraded, data loss risk,
  or cascading failure likely.
- MODERATE: Requires attention soon. Degraded performance, elevated errors, or conditions
  trending toward critical.
- LOW: Worth knowing about but not urgent. Minor anomaly, self-resolving likely, or very
  limited blast radius.
- NOT_A_PROBLEM: False positive, expected behavior, or completely benign.

Respond ONLY with a valid JSON object matching this schema:
{
  "severity": "CRITICAL|MODERATE|LOW|NOT_A_PROBLEM",
  "confidence": 0.0-1.0,
  "reasoning": "explanation",
  "affected_components": ["list", "of", "services"],
  "is_transient": true|false,
  "similar_past_issues": ["known pattern 1", "known pattern 2"]
}
"""


def _build_user_message(enriched_event) -> str:
    return f"""Analyze this infrastructure event:

{enriched_event.summary}

Raw metrics:
{json.dumps([m.model_dump() for m in enriched_event.original.metrics], default=str, indent=2)}

Recent logs:
{json.dumps([l.model_dump() for l in enriched_event.original.logs[-5:]], default=str, indent=2)}

Kubernetes context:
{enriched_event.kubernetes.model_dump_json(indent=2)}

Prometheus context:
{enriched_event.prometheus.model_dump_json(indent=2)}
"""


def _get_litellm_model(provider: str, model: str) -> str:
    if provider == "openrouter":
        return f"openrouter/{model}"
    return model  # anthropic models work directly


async def analyzer_node(state: AgentState) -> AgentState:
    """Call LLM to classify event severity."""
    enriched = state["enriched_event"]
    event_id = enriched.original.event_id

    log.info("analyzer.start", event_id=event_id)

    model = _get_litellm_model(settings.llm.provider, settings.llm.model)

    api_key = (
        settings.llm.anthropic_api_key
        if settings.llm.provider == "anthropic"
        else settings.llm.openrouter_api_key
    )

    response = await acompletion(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(enriched)},
        ],
        max_tokens=settings.llm.max_tokens,
        temperature=settings.llm.temperature,
        api_key=api_key,
        response_format={"type": "json_object"},
    )

    raw_content = response.choices[0].message.content
    try:
        data = json.loads(raw_content)
        analysis = SeverityAnalysis(**data)
    except Exception as exc:
        log.error("analyzer.parse_error", error=str(exc), raw=raw_content)
        # Fallback: treat as MODERATE so we don't silently drop issues
        analysis = SeverityAnalysis(
            severity=Severity.MODERATE,
            confidence=0.5,
            reasoning=f"Parse error, defaulting to MODERATE. Raw: {raw_content[:200]}",
        )

    log.info(
        "analyzer.done",
        event_id=event_id,
        severity=analysis.severity,
        confidence=analysis.confidence,
    )

    return {**state, "analysis": analysis}
