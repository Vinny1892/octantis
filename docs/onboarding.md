---
title: "Onboarding — Zero to Running"
description: "Como subir o Octantis localmente e contribuir com o código"
---

# Onboarding — Zero to Running

## Pré-requisitos

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) instalado
- Docker + Docker Compose (para stack local)
- Chave de API Anthropic (`ANTHROPIC_API_KEY`)

## Setup em 5 minutos

### Opção 1 — Docker Compose (recomendado para testar)

Stack completo: Octantis + Grafana MCP + Grafana + Prometheus + Loki + OTel Collector.

```bash
cd examples/docker-compose
cp ../../.env.example .env
# Edite .env e configure ANTHROPIC_API_KEY

docker compose up -d
```

| Serviço | URL | Credenciais |
|---|---|---|
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | — |
| Octantis OTLP (gRPC) | localhost:4317 | — |
| Octantis OTLP (HTTP) | localhost:4318 | — |
| Octantis Metrics | http://localhost:9091/metrics | — |

### Opção 2 — Desenvolvimento local

```bash
# 1. Clone e entre no diretório
cd /home/vinny/repo/octantis

# 2. Instale as dependências (uv cria o venv automaticamente)
uv sync

# 3. Configure o ambiente
cp .env.example .env
# Edite .env com suas chaves
```

Configuração mínima para rodar localmente:

```env
# .env mínimo para desenvolvimento
ANTHROPIC_API_KEY=sk-ant-...

# Grafana MCP (precisa de um mcp-grafana rodando)
GRAFANA_MCP_URL=http://localhost:8080/sse
GRAFANA_MCP_API_KEY=glsa_...

LOG_LEVEL=DEBUG

# Desabilitar notificações para não spammar Slack/Discord durante dev
# (deixar as vars em branco desabilita o notifier)
SLACK_WEBHOOK_URL=
DISCORD_WEBHOOK_URL=
```

```bash
uv run octantis
```

Saída esperada com `LOG_LEVEL=DEBUG`:

```
2026-04-06T13:00:00Z [info] octantis.starting version=0.2.0
2026-04-06T13:00:00Z [info] mcp.connected server=grafana tools=5
2026-04-06T13:00:00Z [info] octantis.ready otlp_grpc=:4317 otlp_http=:4318 metrics=:9090
```

## Enviando um Evento de Teste

Use `curl` para enviar um evento OTLP/HTTP diretamente ao Octantis:

```bash
# Evento com CPU alta — deve passar pelo TriggerFilter e disparar investigação MCP
curl -X POST http://localhost:4318/v1/metrics \
  -H "Content-Type: application/json" \
  -d '{
    "resourceMetrics": [{
      "resource": {
        "attributes": [
          {"key": "service.name", "value": {"stringValue": "api-server"}},
          {"key": "k8s.namespace.name", "value": {"stringValue": "production"}},
          {"key": "k8s.pod.name", "value": {"stringValue": "api-server-abc123"}},
          {"key": "k8s.deployment.name", "value": {"stringValue": "api-server"}}
        ]
      },
      "scopeMetrics": [{
        "metrics": [{
          "name": "cpu_usage",
          "unit": "%",
          "gauge": {
            "dataPoints": [{"asDouble": 95.0}]
          }
        }]
      }]
    }]
  }'
```

```bash
# Evento benigno — deve ser dropado pelo TriggerFilter (HealthCheckRule)
curl -X POST http://localhost:4318/v1/logs \
  -H "Content-Type: application/json" \
  -d '{
    "resourceLogs": [{
      "resource": {"attributes": [
        {"key": "service.name", "value": {"stringValue": "api-server"}}
      ]},
      "scopeLogs": [{"logRecords": [
        {"body": {"stringValue": "GET /healthz HTTP/1.1 200 OK"}, "severityText": "INFO"}
      ]}]
    }]
  }'
```

Com `LOG_LEVEL=DEBUG`, o segundo evento deve gerar:

```
[debug] trigger.rule_matched rule=health_check decision=drop reason="health probe log: GET /healthz HTTP/1.1 200 OK"
```

## Rodando os Testes

```bash
uv run pytest                          # todos os testes (98)
uv run pytest tests/test_trigger_filter.py -v  # só trigger filter
uv run pytest tests/test_investigator.py -v    # só investigator
uv run pytest -k "cooldown" -v         # por nome
```

Todos os testes usam mocks — nenhuma chamada real ao LLM, MCP, ou APIs externas.

### Lint e Formatação

```bash
uv run ruff check src/ tests/         # lint
uv run ruff format src/ tests/        # auto-format
```

---

## Mapa de Leitura do Código

Dependendo do que você quer entender ou modificar:

### "Quero ajustar o que passa para o LLM"
→ `src/octantis/pipeline/trigger_filter.py` — adicione/modifique regras
→ `src/octantis/pipeline/cooldown.py:21` — ajuste o fingerprint
→ `.env` — `PIPELINE_*` para tunar sem alterar código

### "Quero mudar como o LLM investiga os eventos"
→ `src/octantis/graph/nodes/investigator.py:28` — `INVESTIGATION_SYSTEM_PROMPT`
→ `src/octantis/mcp_client/manager.py` — conexão MCP e descoberta de ferramentas
→ `.env` — `INVESTIGATION_*` para ajustar budget e timeouts

### "Quero mudar como o LLM classifica os eventos"
→ `src/octantis/graph/nodes/analyzer.py:14` — `SYSTEM_PROMPT`
→ `src/octantis/models/analysis.py` — adicione campos ao `SeverityAnalysis`

### "Quero mudar o plano de ação gerado"
→ `src/octantis/graph/nodes/planner.py:14` — `SYSTEM_PROMPT`
→ `src/octantis/models/action_plan.py` — adicione `StepType` ou campos

### "Quero adicionar um canal de notificação"
→ Crie `src/octantis/notifiers/pagerduty.py` implementando `.send(investigation, analysis, action_plan)`
→ Instancie e chame em `src/octantis/graph/nodes/notifier.py`
→ Adicione settings em `src/octantis/config.py`

### "Quero adicionar métricas internas"
→ `src/octantis/metrics.py` — defina novos Counters/Histograms
→ Instrumente nos nós relevantes

### "Quero entender o formato OTLP"
→ `src/octantis/receivers/parser.py` — OTLP Protobuf/JSON → InfraEvent
→ Os campos `resourceMetrics` e `resourceLogs` seguem o schema OTLP/JSON

---

## Variáveis de Ambiente — Referência Completa

| Variável | Default | Descrição |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG / INFO / WARNING / ERROR` |
| `MIN_SEVERITY_TO_NOTIFY` | `MODERATE` | Severidade mínima para acionar Slack/Discord |
| `LLM_PROVIDER` | `anthropic` | `anthropic` ou `openrouter` |
| `LLM_MODEL` | `claude-sonnet-4-6` | Model ID para analyzer e planner |
| `LLM_INVESTIGATION_MODEL` | (= LLM_MODEL) | Model ID para investigator (opcional) |
| `ANTHROPIC_API_KEY` | — | Chave Anthropic (obrigatória se provider=anthropic) |
| `OPENROUTER_API_KEY` | — | Chave OpenRouter (obrigatória se provider=openrouter) |
| `GRAFANA_MCP_URL` | — | URL SSE do Grafana MCP (obrigatório) |
| `GRAFANA_MCP_API_KEY` | — | API key do Grafana service account |
| `K8S_MCP_URL` | — | URL SSE do K8s MCP (opcional, recomendado) |
| `INVESTIGATION_MAX_QUERIES` | `10` | Máximo de queries MCP por investigação |
| `INVESTIGATION_TIMEOUT_SECONDS` | `60` | Timeout total da investigação |
| `INVESTIGATION_QUERY_TIMEOUT_SECONDS` | `10` | Timeout por query MCP |
| `OTLP_GRPC_PORT` | `4317` | Porta do receiver gRPC |
| `OTLP_HTTP_PORT` | `4318` | Porta do receiver HTTP |
| `OTLP_GRPC_ENABLED` | `true` | Habilitar receiver gRPC |
| `OTLP_HTTP_ENABLED` | `true` | Habilitar receiver HTTP |
| `OTLP_QUEUE_MAX_SIZE` | `1000` | Tamanho máximo da fila de eventos |
| `METRICS_PORT` | `9090` | Porta das métricas Prometheus |
| `METRICS_ENABLED` | `true` | Habilitar endpoint de métricas |
| `SLACK_WEBHOOK_URL` | — | Incoming webhook URL (vazio = desabilitado) |
| `SLACK_BOT_TOKEN` | — | Bot token (alternativa ao webhook) |
| `SLACK_CHANNEL` | `#infra-alerts` | Channel (só usado com bot token) |
| `DISCORD_WEBHOOK_URL` | — | Webhook URL (vazio = desabilitado) |
| `PIPELINE_CPU_THRESHOLD` | `75.0` | % CPU para considerar anômalo |
| `PIPELINE_MEMORY_THRESHOLD` | `80.0` | % memória para considerar anômalo |
| `PIPELINE_ERROR_RATE_THRESHOLD` | `0.01` | req/s de erros para considerar anômalo |
| `PIPELINE_BENIGN_PATTERNS` | `""` | Regexes separados por vírgula para sempre dropar |
| `PIPELINE_COOLDOWN_SECONDS` | `300` | Segundos de supressão por fingerprint |
| `PIPELINE_COOLDOWN_MAX_ENTRIES` | `1000` | Máximo de fingerprints em memória |
