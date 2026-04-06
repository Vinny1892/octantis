---
title: "Octantis — Visão Geral da Arquitetura"
description: "Como o agente de monitoramento inteligente funciona de ponta a ponta"
---

# Octantis — Visão Geral da Arquitetura

Octantis é um agente de IA que monitora infraestrutura EKS/Kubernetes de forma inteligente. Em vez de disparar alertas para todo threshold breachado, ele usa um LLM para avaliar o **impacto operacional real** — distinguindo um crash genuíno de um falso positivo de uma métrica ruidosa.

## O Problema que o Octantis Resolve

Sistemas de monitoramento tradicionais geram alertas baseados em thresholds simples:
- "CPU > 80% → alerta"
- "Restarts > 2 → alerta"

Isso resulta em **alert fatigue**: a equipe ignora os alertas porque 90% são ruído. O Octantis inverte a lógica — ao invés de alertar por threshold, ele **investiga autonomamente** via MCP (Model Context Protocol), consultando Grafana (PromQL/LogQL) e Kubernetes para montar o contexto completo antes de decidir se o problema merece atenção humana.

## Fluxo de Dados Completo

```mermaid
%%{init: {"theme": "dark", "themeVariables": {"primaryColor": "#2d333b", "primaryBorderColor": "#6d5dfc", "primaryTextColor": "#e6edf3", "lineColor": "#8b949e", "secondaryColor": "#161b22", "tertiaryColor": "#1c2128"}}}%%
flowchart TD
    OC["OTel Collector\n(serviços K8s)"]:::ext

    subgraph receiver["OTLP Receiver  (src/octantis/receivers/)"]
        GRPC["gRPC Server\n:4317"]:::pipe
        HTTP["HTTP Server\n:4318"]:::pipe
        QUEUE["asyncio.Queue\nInfraEvent"]:::pipe
    end

    subgraph pipeline["Pipeline de Filtragem  (src/octantis/pipeline/)"]
        TF["TriggerFilter\nRegras determinísticas"]:::pipe
        CD["FingerprintCooldown\nDeduplicação por fingerprint"]:::pipe
    end

    subgraph agent["LangGraph Workflow  (src/octantis/graph/)"]
        INV["investigate\nReAct loop via MCP"]:::node
        AN["analyze\nLLM classifica severidade"]:::node
        RT{{"should_notify?\nCRITICAL / MODERATE"}}:::cond
        PL["plan\nLLM gera plano de ação"]:::node
        NO["notify\nSlack + Discord"]:::node
    end

    subgraph mcp["MCP Servers"]
        GF["Grafana MCP\nPromQL / LogQL"]:::ext
        K8["K8s MCP\n(opcional)"]:::ext
    end

    OC -->|"OTLP/gRPC"| GRPC
    OC -->|"OTLP/HTTP"| HTTP
    GRPC --> QUEUE
    HTTP --> QUEUE
    QUEUE -->|"AsyncIterator[InfraEvent]"| TF
    TF -->|"PASS"| CD
    TF -->|"DROP ❌"| VOID1[" "]:::void
    CD -->|"novo fingerprint"| INV
    CD -->|"duplicata ❌"| VOID2[" "]:::void
    INV -.->|"tool calls"| GF
    INV -.->|"tool calls"| K8
    INV --> AN
    AN --> RT
    RT -->|"severidade ≥ threshold"| PL
    RT -->|"LOW / NOT_A_PROBLEM"| END1[" "]:::void
    PL --> NO

    classDef ext fill:#1c2128,stroke:#6d5dfc,color:#e6edf3
    classDef pipe fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
    classDef node fill:#2d333b,stroke:#30363d,color:#e6edf3
    classDef cond fill:#1c2128,stroke:#ffa657,color:#e6edf3
    classDef void fill:none,stroke:none
```

## Componentes Principais

| Módulo | Responsabilidade | Arquivo chave |
|---|---|---|
| **Receiver** | Recebe eventos OTLP via gRPC (:4317) e HTTP (:4318) | `receivers/` |
| **Pipeline** | Decide o que vale o custo do LLM | `pipeline/` |
| **MCP Client** | Conexão SSE com Grafana MCP e K8s MCP | `mcp_client/manager.py` |
| **Graph** | Orquestra o workflow LangGraph | `graph/workflow.py` |
| **Metrics** | 9 métricas Prometheus em `:9090/metrics` | `metrics.py` |
| **Notifiers** | Formata e envia Slack Block Kit / Discord Embeds | `notifiers/` |
| **Config** | Toda configuração via env vars | `config.py` |

## Estrutura de Diretórios

```
src/octantis/
├── main.py                  # Entrypoint — monta e executa o pipeline
├── config.py                # Pydantic BaseSettings (todas as configs via .env)
├── metrics.py               # 9 métricas Prometheus + HTTP server
├── pipeline/
│   ├── trigger_filter.py    # ← Porta de entrada: regras determinísticas
│   └── cooldown.py          # ← Deduplicação por fingerprint + cooldown
├── receivers/
│   ├── receiver.py          # OTLPReceiver — orquestra gRPC + HTTP + asyncio.Queue
│   ├── grpc_server.py       # gRPC servicer (MetricsService, LogsService, TraceService)
│   ├── http_server.py       # aiohttp server (/v1/metrics, /v1/logs, /v1/traces)
│   └── parser.py            # OTLP Protobuf/JSON → InfraEvent
├── mcp_client/
│   └── manager.py           # MCPClientManager — SSE connections + tool discovery
├── graph/
│   ├── workflow.py          # StateGraph LangGraph
│   ├── state.py             # AgentState (TypedDict)
│   └── nodes/
│       ├── investigator.py  # Nó: ReAct loop com ferramentas MCP
│       ├── analyzer.py      # Nó: LLM classifica CRITICAL/MODERATE/LOW/NOT_A_PROBLEM
│       ├── planner.py       # Nó: LLM gera plano de remediação
│       └── notifier.py      # Nó: Slack + Discord
├── notifiers/
│   ├── slack.py             # Block Kit com cores por severidade
│   └── discord.py           # Embeds com cores por severidade
└── models/
    ├── event.py             # InfraEvent, InvestigationResult, MCPQueryRecord
    ├── analysis.py          # SeverityAnalysis, Severity enum
    └── action_plan.py       # ActionPlan, ActionStep
```

## Modelos de Dados Centrais

O dado flui por quatro formas ao longo do pipeline:

```mermaid
%%{init: {"theme": "dark", "themeVariables": {"primaryColor": "#2d333b", "primaryBorderColor": "#6d5dfc", "primaryTextColor": "#e6edf3", "lineColor": "#8b949e"}}}%%
classDiagram
    direction LR

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

## Configuração Rápida

```bash
cp .env.example .env
# Editar credenciais e URLs

uv sync
uv run octantis
```

Ou com Docker Compose (stack completo):

```bash
cd examples/docker-compose
cp ../../.env.example .env
# Editar ANTHROPIC_API_KEY
docker compose up -d
```

Ver [Pipeline de Filtragem](./pipeline.md) para entender como os eventos são triados antes de chegar ao LLM.
Ver [O Agente LangGraph](./agent.md) para entender o workflow de investigação, análise e notificação.
