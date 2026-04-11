---
title: "Octantis — Architecture Overview"
description: "How the intelligent monitoring agent works end-to-end"
---

# Octantis — Architecture Overview

Octantis is an AI agent that intelligently monitors infrastructure. Instead of firing alerts for every breached threshold, it uses an LLM to evaluate the **real operational impact** — distinguishing a genuine crash from a false positive or a noisy metric.

## List of Contents

- [The Problem Octantis Solves](#the-problem-octantis-solves)
- [Complete Data Flow](#complete-data-flow)
- [Main Components](#main-components)
- [Directory Structure](#directory-structure)
- [Core Data Models](#core-data-models)
- [Quick Configuration](#quick-configuration)

## The Problem Octantis Solves

Traditional monitoring systems generate alerts based on simple thresholds:
- "CPU > 80% → alert"
- "Restarts > 2 → alert"

This results in **alert fatigue**: teams ignore alerts because 90% are noise. Octantis inverts the logic — instead of alerting on thresholds, it **autonomously investigates** via MCP (Model Context Protocol), querying Grafana (PromQL/LogQL) and optionally Kubernetes to build the full context before deciding whether the problem deserves human attention.

## Complete Data Flow

```mermaid
%%{init: {"theme": "dark", "themeVariables": {"primaryColor": "#2d333b", "primaryBorderColor": "#6d5dfc", "primaryTextColor": "#e6edf3", "lineColor": "#8b949e", "secondaryColor": "#161b22", "tertiaryColor": "#1c2128"}}}%%
flowchart TD
    OC["OTel Collector\n(infrastructure services)"]:::ext

    subgraph receiver["OTLP Receiver  (src/octantis/receivers/)"]
        GRPC["gRPC Server\n:4317"]:::pipe
        HTTP["HTTP Server\n:4318"]:::pipe
        QUEUE["asyncio.Queue\nInfraEvent"]:::pipe
    end

    subgraph pipeline["Filter Pipeline  (src/octantis/pipeline/)"]
        TF["TriggerFilter\nDeterministic rules"]:::pipe
        CD["FingerprintCooldown\nFingerprint deduplication"]:::pipe
    end

    subgraph agent["LangGraph Workflow  (src/octantis/graph/)"]
        INV["investigate\nReAct loop via MCP"]:::node
        AN["analyze\nLLM classifies severity"]:::node
        RT{{"should_notify?\nCRITICAL / MODERATE"}}:::cond
        PL["plan\nLLM generates action plan"]:::node
        NO["notify\nSlack + Discord"]:::node
    end

    subgraph detect["Environment Detection  (src/octantis/pipeline/)"]
        ED["EnvironmentDetector\nK8s / Docker / AWS"]:::pipe
    end

    subgraph mcp["MCP Servers (slot model)"]
        GF["Grafana MCP\nPromQL / LogQL\n(observability slot)"]:::ext
        K8["K8s MCP\n(platform slot)"]:::ext
        DK["Docker MCP\n(platform slot)"]:::ext
        AW["AWS MCP\n(platform slot)"]:::ext
    end

    OC -->|"OTLP/gRPC"| GRPC
    OC -->|"OTLP/HTTP"| HTTP
    GRPC --> QUEUE
    HTTP --> QUEUE
    QUEUE -->|"AsyncIterator[InfraEvent]"| TF
    TF -->|"PASS"| CD
    TF -->|"DROP ❌"| VOID1[" "]:::void
    CD -->|"new fingerprint"| ED
    CD -->|"duplicate ❌"| VOID2[" "]:::void
    ED -->|"typed resource"| INV
    INV -.->|"tool calls"| GF
    INV -.->|"tool calls"| K8
    INV -.->|"tool calls"| DK
    INV -.->|"tool calls"| AW
    INV --> AN
    AN --> RT
    RT -->|"severity ≥ threshold"| PL
    RT -->|"LOW / NOT_A_PROBLEM"| END1[" "]:::void
    PL --> NO

    classDef ext fill:#1c2128,stroke:#6d5dfc,color:#e6edf3
    classDef pipe fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
    classDef node fill:#2d333b,stroke:#30363d,color:#e6edf3
    classDef cond fill:#1c2128,stroke:#ffa657,color:#e6edf3
    classDef void fill:none,stroke:none
```

## Main Components

| Module | Responsibility | Key file |
|---|---|---|
| **Receiver** | Receives OTLP events via gRPC (:4317) and HTTP (:4318) | `receivers/` |
| **Pipeline** | Decides what is worth the LLM cost + environment detection | `pipeline/` |
| **MCP Client** | Registry-based SSE connections to MCP servers (slot model: observability + platform) | `mcp_client/manager.py` |
| **Graph** | Orchestrates the LangGraph workflow | `graph/workflow.py` |
| **Metrics** | 9 Prometheus metrics on `:9090/metrics` | `metrics.py` |
| **Notifiers** | Formats and sends Slack Block Kit / Discord Embeds | `notifiers/` |
| **Helm Chart** | Modular Kubernetes deployment with toggleable components | `charts/octantis/` |
| **kube-prometheus-stack** | Optional monitoring stack (Prometheus + Grafana + Alertmanager) via subchart | `charts/octantis/` |
| **Config** | All configuration via env vars | `config.py` |

## Directory Structure

```
src/octantis/
├── main.py                  # Entrypoint — assembles and runs the pipeline
├── config.py                # Pydantic BaseSettings (all config via .env)
├── metrics.py               # 9 Prometheus metrics + HTTP server
├── pipeline/
│   ├── trigger_filter.py    # ← Entry gate: deterministic rules
│   ├── cooldown.py          # ← Fingerprint deduplication + cooldown
│   └── environment_detector.py  # ← Promotes OTelResource to K8s/Docker/AWS subclass
├── receivers/
│   ├── receiver.py          # OTLPReceiver — orchestrates gRPC + HTTP + asyncio.Queue
│   ├── grpc_server.py       # gRPC servicer (MetricsService, LogsService, TraceService)
│   ├── http_server.py       # aiohttp server (/v1/metrics, /v1/logs, /v1/traces)
│   └── parser.py            # OTLP Protobuf/JSON → InfraEvent
├── mcp_client/
│   └── manager.py           # MCPClientManager — SSE connections + tool discovery
├── graph/
│   ├── workflow.py          # StateGraph LangGraph
│   ├── state.py             # AgentState (TypedDict)
│   └── nodes/
│       ├── investigator.py  # Node: ReAct loop with MCP tools
│       ├── analyzer.py      # Node: LLM classifies CRITICAL/MODERATE/LOW/NOT_A_PROBLEM
│       ├── planner.py       # Node: LLM generates remediation plan
│       └── notifier.py      # Node: Slack + Discord
├── notifiers/
│   ├── slack.py             # Block Kit with severity-based colors
│   └── discord.py           # Embeds with severity-based colors
└── models/
    ├── event.py             # InfraEvent, InvestigationResult, MCPQueryRecord
    ├── analysis.py          # SeverityAnalysis, Severity enum
    └── action_plan.py       # ActionPlan, ActionStep
```

## Core Data Models

Data flows through four shapes along the pipeline:

```mermaid
%%{init: {"theme": "dark", "themeVariables": {"primaryColor": "#2d333b", "primaryBorderColor": "#6d5dfc", "primaryTextColor": "#e6edf3", "lineColor": "#8b949e"}}}%%
classDiagram
    direction LR

    class OTelResource {
        +service_name: str
        +host_name: str
        +extra: dict
        +context_summary() str
    }

    class K8sResource {
        +k8s_namespace: str
        +k8s_pod_name: str
        +k8s_deployment_name: str
    }

    class DockerResource {
        +container_id: str
        +container_name: str
        +image_name: str
    }

    class AWSResource {
        +instance_id: str
        +cloud_region: str
        +aws_service: str
    }

    OTelResource <|-- K8sResource
    OTelResource <|-- DockerResource
    OTelResource <|-- AWSResource

    class InfraEvent {
        +event_id: str
        +event_type: str
        +source: str
        +resource: OTelResource
        +metrics: list[MetricDataPoint]
        +logs: list[LogRecord]
    }

    class InvestigationResult {
        +original_event: InfraEvent
        +queries_executed: list[MCPQueryRecord]
        +evidence_summary: str
        +mcp_degraded: bool
        +budget_exhausted: bool
        +summary() str
    }

    class SeverityAnalysis {
        +severity: Severity
        +confidence: float
        +reasoning: str
        +affected_components: list[str]
        +is_transient: bool
    }

    class ActionPlan {
        +title: str
        +steps: list[ActionStep]
        +escalate_to: list[str]
        +estimated_resolution_minutes: int
    }

    InfraEvent --> InvestigationResult : investigate node
    InvestigationResult --> SeverityAnalysis : analyzer node
    SeverityAnalysis --> ActionPlan : planner node
```

## Quick Configuration

```bash
cp .env.example .env
# Edit credentials and URLs

uv sync
uv run octantis
```

For Kubernetes deployment, use the Helm chart:

```bash
helm install octantis oci://ghcr.io/vinny1892/charts/octantis -n monitoring
```

See [`charts/octantis/README.md`](../charts/octantis/README.md) for the full configuration reference.

See [Filter Pipeline](./PIPELINE.md) to understand how events are triaged before reaching the LLM.
See [The LangGraph Agent](./AGENT.md) to understand the investigation, analysis, and notification workflow.
