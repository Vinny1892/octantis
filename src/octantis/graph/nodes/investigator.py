"""Investigator node: LLM-driven investigation via Grafana MCP tools.

Replaces the old collector node. Instead of pre-fetching a fixed set of
metrics, the LLM autonomously queries Prometheus (PromQL), Loki (LogQL),
and optionally Kubernetes via MCP tool calling in a ReAct loop.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING, Annotated, Any

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from octantis.config import settings
from octantis.graph.nodes.utils import language_instruction
from octantis.graph.state import AgentState
from octantis.models.event import InfraEvent, InvestigationResult, MCPQueryRecord

if TYPE_CHECKING:
    from octantis.mcp_client import MCPClientManager

log = structlog.get_logger(__name__)

INVESTIGATION_SYSTEM_PROMPT = """\
You are Octantis, an expert SRE/infrastructure analyst investigating a Kubernetes \
infrastructure event.

You have access to observability tools that let you query real-time data:
- **PromQL queries** (Prometheus): CPU, memory, network, error rates, custom metrics
- **LogQL queries** (Loki): application logs, error logs, container logs
- **Kubernetes queries** (if available): pod status, events, deployments

## Investigation Strategy
1. Start by understanding the trigger event context
2. Query broad metrics first (CPU, memory, error rate for the affected workload)
3. Based on initial findings, drill down into specific areas
4. Query logs for error patterns and stack traces
5. Conclude when you have enough evidence to classify severity

## Common PromQL Patterns
- CPU usage: `sum(rate(container_cpu_usage_seconds_total{namespace="NS",pod=~"POD.*"}[5m])) * 100`
- Memory usage: `container_memory_working_set_bytes{namespace="NS",pod=~"POD.*"}`
- Error rate: `sum(rate(http_requests_total{namespace="NS",status=~"5.."}[5m]))`
- Restarts: `kube_pod_container_status_restarts_total{namespace="NS",pod=~"POD.*"}`
- Pod ready: `kube_pod_status_ready{namespace="NS",pod=~"POD.*"}`

## Common LogQL Patterns
- Error logs: `{namespace="NS",pod=~"POD.*"} |= "error" | logfmt`
- Recent logs: `{namespace="NS",pod=~"POD.*"} | logfmt | level=~"error|warn"`

## Rules
- Be efficient: don't repeat the same query
- If a query returns empty, try a broader query or different metric
- If you have enough evidence, conclude — don't query unnecessarily
- Always explain your reasoning when concluding

When you are done investigating, provide a comprehensive summary of your findings \
as your final message. Include what you found, what it means, and your assessment.
"""


def _build_trigger_context(event: InfraEvent) -> str:
    """Build human-readable trigger context for the LLM."""
    parts = [
        "## Trigger Event",
        f"- **Type**: {event.event_type}",
        f"- **Source**: {event.source}",
        f"- **Service**: {event.resource.service_name or 'unknown'}",
        f"- **Namespace**: {event.resource.k8s_namespace or 'unknown'}",
    ]
    if event.resource.k8s_pod_name:
        parts.append(f"- **Pod**: {event.resource.k8s_pod_name}")
    if event.resource.k8s_deployment_name:
        parts.append(f"- **Deployment**: {event.resource.k8s_deployment_name}")
    if event.resource.k8s_node_name:
        parts.append(f"- **Node**: {event.resource.k8s_node_name}")

    if event.metrics:
        parts.append("\n## Trigger Metrics")
        for m in event.metrics[:10]:
            parts.append(f"- {m.name} = {m.value} {m.unit or ''}")

    if event.logs:
        parts.append("\n## Trigger Logs")
        for rec in event.logs[-5:]:
            sev = rec.severity_text or "INFO"
            parts.append(f"- [{sev}] {rec.body[:300]}")

    return "\n".join(parts)


def _get_litellm_model(provider: str, model: str) -> str:
    if provider == "openrouter":
        return f"openrouter/{model}"
    return model


def _classify_datasource(tool_name: str) -> str:
    """Classify a tool call into a datasource category."""
    name_lower = tool_name.lower()
    if "promql" in name_lower or "prometheus" in name_lower or "metric" in name_lower:
        return "promql"
    if "logql" in name_lower or "loki" in name_lower or "log" in name_lower:
        return "logql"
    if "k8s" in name_lower or "kube" in name_lower or "pod" in name_lower:
        return "k8s"
    return "promql"  # default to promql for unknown grafana tools


class _InvestigationState(AgentState):
    """Extended state for the investigation subgraph."""

    messages: Annotated[Sequence[BaseMessage], lambda x, y: list(x) + list(y)]
    query_count: int
    query_records: list[dict[str, Any]]


async def investigate_node(
    state: AgentState,
    mcp_manager: MCPClientManager,
) -> AgentState:
    """Run LLM-driven investigation via MCP tool calling."""
    event = state["event"]
    event_id = event.event_id
    start_time = time.monotonic()

    log.info(
        "investigation.start", event_id=event_id, mcp_servers=mcp_manager.get_degraded_servers()
    )

    tools = mcp_manager.get_tools()
    mcp_servers_used = [
        name
        for name in ["grafana", "k8s"]
        if name not in [s.split("/")[-1] for s in mcp_manager.get_degraded_servers()]
    ]

    # Degraded mode: no tools available
    if not tools:
        log.warning(
            "investigation.degraded",
            event_id=event_id,
            unavailable_servers=mcp_manager.get_degraded_servers(),
        )

        from octantis.metrics import INVESTIGATION_DURATION

        duration = time.monotonic() - start_time
        INVESTIGATION_DURATION.observe(duration)

        result = InvestigationResult(
            original_event=event,
            evidence_summary=f"MCP servers unavailable. Analysis based on trigger data only: {_build_trigger_context(event)}",
            mcp_servers_used=[],
            mcp_degraded=True,
            investigation_duration_s=duration,
        )
        return {**state, "investigation": result}

    # Run the ReAct investigation loop
    investigation_model = settings.investigation.model or settings.llm.model
    model_id = _get_litellm_model(settings.llm.provider, investigation_model)
    api_key = (
        settings.llm.anthropic_api_key
        if settings.llm.provider == "anthropic"
        else settings.llm.openrouter_api_key
    )

    max_queries = settings.investigation.max_queries
    timeout = settings.investigation.timeout_seconds

    trigger_context = _build_trigger_context(event)
    query_records: list[MCPQueryRecord] = []
    query_count = 0
    budget_exhausted = False
    mcp_degraded = mcp_manager.is_degraded
    total_input_tokens = 0
    total_output_tokens = 0

    messages: list[BaseMessage] = [
        SystemMessage(
            content=INVESTIGATION_SYSTEM_PROMPT + language_instruction(settings.language)
        ),
        HumanMessage(content=f"Investigate this infrastructure event:\n\n{trigger_context}"),
    ]

    from litellm import acompletion

    tool_schemas = [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.args_schema.model_json_schema()
                if hasattr(t, "args_schema")
                and t.args_schema
                and hasattr(t.args_schema, "model_json_schema")
                else t.args_schema
                if isinstance(t.args_schema, dict)
                else {"type": "object", "properties": {}},
            },
        }
        for t in tools
    ]
    tools_by_name = {t.name: t for t in tools}

    evidence_summary = ""

    try:
        async with asyncio.timeout(timeout):
            while True:
                # Check budget before calling LLM
                if query_count >= max_queries:
                    budget_exhausted = True
                    log.info(
                        "investigation.budget_exhausted",
                        event_id=event_id,
                        queries_completed=query_count,
                    )
                    # Ask LLM to conclude with available data
                    messages.append(
                        HumanMessage(
                            content="Query budget exhausted. Provide your final investigation summary based on the data collected so far."
                        )
                    )
                    response = await acompletion(
                        model=model_id,
                        messages=[
                            {"role": m.type if m.type != "human" else "user", "content": m.content}
                            for m in messages
                            if isinstance(m.content, str)
                        ],
                        max_tokens=settings.llm.max_tokens,
                        temperature=settings.llm.temperature,
                        api_key=api_key,
                    )
                    usage = response.get("usage", {})
                    total_input_tokens += getattr(usage, "prompt_tokens", 0)
                    total_output_tokens += getattr(usage, "completion_tokens", 0)
                    evidence_summary = response.choices[0].message.content
                    break

                # Call LLM with tools
                litellm_messages = []
                for m in messages:
                    if isinstance(m, SystemMessage):
                        litellm_messages.append({"role": "system", "content": m.content})
                    elif isinstance(m, HumanMessage):
                        litellm_messages.append({"role": "user", "content": m.content})
                    elif isinstance(m, AIMessage):
                        msg_dict: dict[str, Any] = {"role": "assistant", "content": m.content or ""}
                        if m.tool_calls:
                            msg_dict["tool_calls"] = [
                                {
                                    "id": tc["id"],
                                    "type": "function",
                                    "function": {
                                        "name": tc["name"],
                                        "arguments": json.dumps(tc["args"])
                                        if isinstance(tc["args"], dict)
                                        else tc["args"],
                                    },
                                }
                                for tc in m.tool_calls
                            ]
                        litellm_messages.append(msg_dict)
                    elif isinstance(m, ToolMessage):
                        litellm_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": m.tool_call_id,
                                "content": m.content,
                            }
                        )

                response = await acompletion(
                    model=model_id,
                    messages=litellm_messages,
                    tools=tool_schemas if tools else None,
                    max_tokens=settings.llm.max_tokens,
                    temperature=settings.llm.temperature,
                    api_key=api_key,
                )

                usage = response.get("usage", {})
                total_input_tokens += getattr(usage, "prompt_tokens", 0)
                total_output_tokens += getattr(usage, "completion_tokens", 0)

                choice = response.choices[0]
                assistant_msg = choice.message

                # No tool calls — LLM is done investigating
                if not assistant_msg.tool_calls:
                    evidence_summary = assistant_msg.content or ""
                    messages.append(AIMessage(content=evidence_summary))
                    break

                # Process tool calls
                ai_tool_calls = []
                for tc in assistant_msg.tool_calls:
                    ai_tool_calls.append(
                        {
                            "id": tc.id,
                            "name": tc.function.name,
                            "args": json.loads(tc.function.arguments)
                            if isinstance(tc.function.arguments, str)
                            else tc.function.arguments,
                        }
                    )

                messages.append(
                    AIMessage(content=assistant_msg.content or "", tool_calls=ai_tool_calls)
                )

                for tc in assistant_msg.tool_calls:
                    tool_name = tc.function.name
                    tool_args = (
                        json.loads(tc.function.arguments)
                        if isinstance(tc.function.arguments, str)
                        else tc.function.arguments
                    )
                    query_str = json.dumps(tool_args)
                    datasource = _classify_datasource(tool_name)

                    query_start = time.monotonic()
                    tool_error = None
                    result_str = ""

                    try:
                        tool = tools_by_name.get(tool_name)
                        if tool:
                            async with asyncio.timeout(
                                settings.investigation.query_timeout_seconds
                            ):
                                result = await tool.ainvoke(tool_args)
                                result_str = str(result)[:2000]
                        else:
                            result_str = f"Tool '{tool_name}' not found"
                            tool_error = "tool_not_found"
                    except TimeoutError:
                        result_str = (
                            f"Query timed out after {settings.investigation.query_timeout_seconds}s"
                        )
                        tool_error = "timeout"
                        log.warning(
                            "mcp.query_timeout",
                            event_id=event_id,
                            tool=tool_name,
                            query=query_str[:100],
                        )

                        from octantis.metrics import MCP_ERRORS

                        MCP_ERRORS.labels(error_type="timeout").inc()
                    except Exception as exc:
                        result_str = f"Query error: {exc}"
                        tool_error = "query_error"
                        log.warning(
                            "mcp.query_error", event_id=event_id, tool=tool_name, error=str(exc)
                        )

                        from octantis.metrics import MCP_ERRORS

                        MCP_ERRORS.labels(error_type="query").inc()

                    query_duration_ms = (time.monotonic() - query_start) * 1000
                    query_count += 1

                    log.debug(
                        "investigation.query",
                        event_id=event_id,
                        tool=tool_name,
                        query=query_str[:100],
                        duration_ms=round(query_duration_ms, 1),
                    )

                    query_records.append(
                        MCPQueryRecord(
                            tool_name=tool_name,
                            query=query_str,
                            result_summary=result_str[:500],
                            duration_ms=query_duration_ms,
                            datasource=datasource,
                            error=tool_error,
                        )
                    )

                    # Record metrics
                    from octantis.metrics import INVESTIGATION_QUERIES, MCP_QUERY_DURATION

                    INVESTIGATION_QUERIES.labels(datasource=datasource).inc()
                    MCP_QUERY_DURATION.labels(datasource=datasource).observe(
                        query_duration_ms / 1000
                    )

                    messages.append(
                        ToolMessage(
                            content=result_str,
                            tool_call_id=tc.id,
                        )
                    )

    except TimeoutError:
        log.warning(
            "investigation.timeout",
            event_id=event_id,
            queries_completed=query_count,
            elapsed_s=round(time.monotonic() - start_time, 1),
        )
        if not evidence_summary:
            evidence_summary = "Investigation timed out. Partial data collected."

    except Exception as exc:
        log.error("investigation.error", event_id=event_id, error=str(exc), exc_info=True)
        evidence_summary = f"Investigation failed: {exc}"

    duration = time.monotonic() - start_time

    from octantis.metrics import (
        INVESTIGATION_DURATION,
        LLM_TOKENS_INPUT,
        LLM_TOKENS_OUTPUT,
        LLM_TOKENS_TOTAL,
    )

    INVESTIGATION_DURATION.observe(duration)
    LLM_TOKENS_INPUT.labels(node="investigate").inc(total_input_tokens)
    LLM_TOKENS_OUTPUT.labels(node="investigate").inc(total_output_tokens)
    LLM_TOKENS_TOTAL.labels(node="investigate").inc(total_input_tokens + total_output_tokens)

    log.info(
        "investigation.done",
        event_id=event_id,
        queries_count=query_count,
        duration_s=round(duration, 1),
        budget_exhausted=budget_exhausted,
        tokens_input=total_input_tokens,
        tokens_output=total_output_tokens,
    )

    result = InvestigationResult(
        original_event=event,
        queries_executed=query_records,
        evidence_summary=evidence_summary,
        mcp_servers_used=mcp_servers_used,
        mcp_degraded=mcp_degraded,
        budget_exhausted=budget_exhausted,
        investigation_duration_s=duration,
        tokens_input=total_input_tokens,
        tokens_output=total_output_tokens,
    )

    return {**state, "investigation": result}
