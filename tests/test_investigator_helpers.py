"""Unit tests for investigator helpers and ReAct loop branches."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octantis.graph.nodes.investigator import (
    _build_trigger_context,
    _classify_datasource,
    investigate_node,
)
from octantis.models.event import (
    AWSResource,
    DockerResource,
    InfraEvent,
    InvestigationResult,
    K8sResource,
    LogRecord,
    MetricDataPoint,
)

# ─── _classify_datasource ─────────────────────────────────────────────────


def test_classify_promql():
    assert _classify_datasource("query_promql") == "promql"
    assert _classify_datasource("search_prometheus") == "promql"
    assert _classify_datasource("get_metric_data") == "promql"


def test_classify_logql():
    assert _classify_datasource("query_logql") == "logql"
    assert _classify_datasource("search_loki") == "logql"
    assert _classify_datasource("get_log_entries") == "logql"


def test_classify_k8s():
    assert _classify_datasource("get_k8s_pods") == "k8s"
    assert _classify_datasource("list_kube_events") == "k8s"
    assert _classify_datasource("describe_pod") == "k8s"


def test_classify_docker():
    assert _classify_datasource("docker_inspect") == "docker"
    assert _classify_datasource("list_container_stats") == "docker"


def test_classify_aws():
    assert _classify_datasource("aws_describe_instances") == "aws"
    assert _classify_datasource("get_ec2_status") == "aws"
    assert _classify_datasource("cloudwatch_get_data") == "aws"
    assert _classify_datasource("list_ecs_tasks") == "aws"


def test_classify_unknown_defaults_promql():
    assert _classify_datasource("some_random_tool") == "promql"


# ─── _build_trigger_context ───────────────────────────────────────────────


def test_build_trigger_context_basic():
    event = InfraEvent(
        event_id="ctx-001",
        event_type="metric",
        source="api-server",
        resource=K8sResource(
            service_name="api-server",
            k8s_namespace="production",
            k8s_pod_name="api-abc",
        ),
    )
    ctx = _build_trigger_context(event)
    assert "## Trigger Event" in ctx
    assert "metric" in ctx
    assert "api-server" in ctx


def test_build_trigger_context_with_metrics():
    event = InfraEvent(
        event_id="ctx-002",
        event_type="metric",
        source="api",
        resource=K8sResource(service_name="api"),
        metrics=[
            MetricDataPoint(name="cpu_usage", value=95.0, unit="%"),
            MetricDataPoint(name="memory_usage", value=80.0),
        ],
    )
    ctx = _build_trigger_context(event)
    assert "## Trigger Metrics" in ctx
    assert "cpu_usage = 95.0 %" in ctx
    assert "memory_usage = 80.0" in ctx


def test_build_trigger_context_with_logs():
    event = InfraEvent(
        event_id="ctx-003",
        event_type="log",
        source="api",
        resource=K8sResource(service_name="api"),
        logs=[
            LogRecord(body="ERROR: connection refused", severity_text="ERROR"),
        ],
    )
    ctx = _build_trigger_context(event)
    assert "## Trigger Logs" in ctx
    assert "[ERROR]" in ctx
    assert "connection refused" in ctx


def test_build_trigger_context_log_no_severity():
    event = InfraEvent(
        event_id="ctx-004",
        event_type="log",
        source="api",
        resource=K8sResource(service_name="api"),
        logs=[LogRecord(body="Some log message")],
    )
    ctx = _build_trigger_context(event)
    assert "[INFO]" in ctx


def test_build_trigger_context_docker():
    event = InfraEvent(
        event_id="ctx-005",
        event_type="metric",
        source="nginx",
        resource=DockerResource(
            service_name="nginx",
            container_name="nginx-1",
            image_name="nginx:1.25",
        ),
    )
    ctx = _build_trigger_context(event)
    assert "Container: nginx-1" in ctx


def test_build_trigger_context_aws():
    event = InfraEvent(
        event_id="ctx-006",
        event_type="metric",
        source="api",
        resource=AWSResource(
            service_name="api",
            instance_id="i-abc123",
            cloud_region="us-east-1",
        ),
    )
    ctx = _build_trigger_context(event)
    assert "Instance: i-abc123" in ctx


# ─── investigate_node ReAct loop with tool calls ──────────────────────────


def _make_mcp_manager(tools=None, degraded=False, degraded_servers=None, connected=None):
    manager = MagicMock()
    manager.get_tools.return_value = tools or []
    manager.is_degraded = degraded
    manager.get_degraded_servers.return_value = degraded_servers or []
    manager.get_connected_servers.return_value = connected or []
    return manager


def _make_event():
    return InfraEvent(
        event_id="react-001",
        event_type="metric",
        source="api-server",
        resource=K8sResource(
            service_name="api-server",
            k8s_namespace="production",
            k8s_pod_name="api-abc",
        ),
        metrics=[MetricDataPoint(name="cpu_usage", value=95.0)],
    )


def _make_tool(name="query_prometheus", description="Query Prometheus"):
    tool = MagicMock()
    tool.name = name
    tool.description = description
    tool.args_schema = None
    return tool


@pytest.mark.asyncio
async def test_investigate_react_one_tool_call():
    """LLM makes one tool call then concludes."""
    event = _make_event()
    tool = _make_tool()
    tool.ainvoke = AsyncMock(return_value="cpu_usage: 95%")
    manager = _make_mcp_manager(tools=[tool], connected=["grafana"])

    # First response: LLM makes a tool call
    tc_mock = MagicMock()
    tc_mock.id = "tc-1"
    tc_mock.function.name = "query_prometheus"
    tc_mock.function.arguments = json.dumps({"query": "rate(cpu[5m])"})

    first_response = MagicMock()
    first_response.choices[0].message.content = ""
    first_response.choices[0].message.tool_calls = [tc_mock]
    first_response.get.return_value = MagicMock(prompt_tokens=200, completion_tokens=50)

    # Second response: LLM concludes
    second_response = MagicMock()
    second_response.choices[0].message.content = "CPU is at 95%, likely OOM issue."
    second_response.choices[0].message.tool_calls = None
    second_response.get.return_value = MagicMock(prompt_tokens=400, completion_tokens=100)

    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return first_response
        return second_response

    state = {"event": event}

    with patch("litellm.acompletion", side_effect=mock_acompletion):
        result = await investigate_node(state, mcp_manager=manager)

    investigation: InvestigationResult = result["investigation"]
    assert len(investigation.queries_executed) == 1
    assert investigation.queries_executed[0].tool_name == "query_prometheus"
    assert investigation.queries_executed[0].datasource == "promql"
    assert "95%" in investigation.evidence_summary
    assert not investigation.budget_exhausted
    assert investigation.mcp_servers_used == ["grafana"]


@pytest.mark.asyncio
async def test_investigate_react_tool_not_found():
    """LLM calls a tool that doesn't exist."""
    event = _make_event()
    tool = _make_tool()
    manager = _make_mcp_manager(tools=[tool], connected=["grafana"])

    tc_mock = MagicMock()
    tc_mock.id = "tc-1"
    tc_mock.function.name = "nonexistent_tool"
    tc_mock.function.arguments = "{}"

    first_response = MagicMock()
    first_response.choices[0].message.content = ""
    first_response.choices[0].message.tool_calls = [tc_mock]
    first_response.get.return_value = MagicMock(prompt_tokens=200, completion_tokens=50)

    second_response = MagicMock()
    second_response.choices[0].message.content = "Tool not found, concluding."
    second_response.choices[0].message.tool_calls = None
    second_response.get.return_value = MagicMock(prompt_tokens=400, completion_tokens=100)

    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        return first_response if call_count == 1 else second_response

    state = {"event": event}

    with patch("litellm.acompletion", side_effect=mock_acompletion):
        result = await investigate_node(state, mcp_manager=manager)

    investigation: InvestigationResult = result["investigation"]
    assert len(investigation.queries_executed) == 1
    assert investigation.queries_executed[0].error == "tool_not_found"


@pytest.mark.asyncio
async def test_investigate_react_tool_exception():
    """Tool invocation raises an exception."""
    event = _make_event()
    tool = _make_tool()
    tool.ainvoke = AsyncMock(side_effect=RuntimeError("Connection refused"))
    manager = _make_mcp_manager(tools=[tool], connected=["grafana"])

    tc_mock = MagicMock()
    tc_mock.id = "tc-1"
    tc_mock.function.name = "query_prometheus"
    tc_mock.function.arguments = json.dumps({"query": "up"})

    first_response = MagicMock()
    first_response.choices[0].message.content = ""
    first_response.choices[0].message.tool_calls = [tc_mock]
    first_response.get.return_value = MagicMock(prompt_tokens=200, completion_tokens=50)

    second_response = MagicMock()
    second_response.choices[0].message.content = "Query failed, concluding."
    second_response.choices[0].message.tool_calls = None
    second_response.get.return_value = MagicMock(prompt_tokens=400, completion_tokens=100)

    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        return first_response if call_count == 1 else second_response

    state = {"event": event}

    with patch("litellm.acompletion", side_effect=mock_acompletion):
        result = await investigate_node(state, mcp_manager=manager)

    investigation: InvestigationResult = result["investigation"]
    assert len(investigation.queries_executed) == 1
    assert investigation.queries_executed[0].error == "query_error"


@pytest.mark.asyncio
async def test_investigate_budget_exhausted():
    """Budget exhaustion triggers conclude message."""
    event = _make_event()
    tool = _make_tool()
    tool.ainvoke = AsyncMock(return_value="data")
    manager = _make_mcp_manager(tools=[tool], connected=["grafana"])

    tc_mock = MagicMock()
    tc_mock.id = "tc-1"
    tc_mock.function.name = "query_prometheus"
    tc_mock.function.arguments = json.dumps({"query": "up"})

    tool_response = MagicMock()
    tool_response.choices[0].message.content = ""
    tool_response.choices[0].message.tool_calls = [tc_mock]
    tool_response.get.return_value = MagicMock(prompt_tokens=200, completion_tokens=50)

    conclude_response = MagicMock()
    conclude_response.choices[0].message.content = "Budget exhausted, partial analysis."
    conclude_response.choices[0].message.tool_calls = None
    conclude_response.get.return_value = MagicMock(prompt_tokens=600, completion_tokens=100)

    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        # Keep returning tool calls until budget hit, then conclude
        if call_count <= 1:
            return tool_response
        return conclude_response

    state = {"event": event}

    with (
        patch("litellm.acompletion", side_effect=mock_acompletion),
        patch("octantis.graph.nodes.investigator.settings") as mock_settings,
    ):
        mock_settings.investigation.model = None
        mock_settings.llm.provider = "anthropic"
        mock_settings.llm.model = "claude-sonnet-4-6"
        mock_settings.llm.max_tokens = 2048
        mock_settings.llm.temperature = 0.1
        mock_settings.investigation.max_queries = 1  # Budget of 1
        mock_settings.investigation.timeout_seconds = 60
        mock_settings.investigation.query_timeout_seconds = 10
        mock_settings.language = "en"

        result = await investigate_node(state, mcp_manager=manager)

    investigation: InvestigationResult = result["investigation"]
    assert investigation.budget_exhausted is True
    assert len(investigation.queries_executed) == 1
