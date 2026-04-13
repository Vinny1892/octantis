# SPDX-License-Identifier: AGPL-3.0-or-later
"""Analyzer node: uses LLM to classify severity of an infrastructure event."""

import json

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
from octantis.models.analysis import Severity, SeverityAnalysis

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = """\
You are Octantis, an expert SRE/infrastructure analyst.
Your job is to assess infrastructure events from a Kubernetes/EKS environment and
classify their real severity — going beyond simple threshold breaches.

You will receive investigation data (MCP query results, evidence summary, trigger event)
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


def _build_user_message(state: AgentState) -> str:
    investigation = state["investigation"]
    event = investigation.original_event

    parts = [
        "Analyze this infrastructure event based on the investigation data:",
        "",
        investigation.summary,
    ]

    if investigation.queries_executed:
        parts.append("\n## MCP Query Results")
        for qr in investigation.queries_executed:
            status = f" [ERROR: {qr.error}]" if qr.error else ""
            parts.append(f"- **{qr.tool_name}** ({qr.datasource}, {qr.duration_ms:.0f}ms){status}")
            parts.append(f"  Query: {qr.query[:200]}")
            parts.append(f"  Result: {qr.result_summary[:300]}")

    if investigation.evidence_summary:
        parts.append(f"\n## Investigation Summary\n{investigation.evidence_summary}")

    if event.metrics:
        parts.append("\n## Raw Trigger Metrics")
        parts.append(json.dumps([m.model_dump() for m in event.metrics], default=str, indent=2))

    if event.logs:
        parts.append("\n## Recent Trigger Logs")
        parts.append(
            json.dumps([rec.model_dump() for rec in event.logs[-5:]], default=str, indent=2)
        )

    if investigation.mcp_degraded:
        parts.append(
            "\n**WARNING**: MCP servers were unavailable during investigation. "
            "Analysis is based on trigger data only and may be imprecise."
        )

    return "\n".join(parts)


async def analyzer_node(state: AgentState) -> AgentState:
    """Call LLM to classify event severity."""
    investigation = state["investigation"]
    event_id = investigation.original_event.event_id

    log.info("analyzer.start", event_id=event_id)

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

    LLM_TOKENS_INPUT.labels(node="analyze").inc(input_tokens)
    LLM_TOKENS_OUTPUT.labels(node="analyze").inc(output_tokens)
    LLM_TOKENS_TOTAL.labels(node="analyze").inc(input_tokens + output_tokens)

    raw_content = response.choices[0].message.content
    try:
        data = parse_llm_json(raw_content)
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
