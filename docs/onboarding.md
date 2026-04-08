---
title: "Onboarding — Zero to Running"
description: "Como subir o Octantis e contribuir com o código"
---

# Onboarding — Zero to Running

## Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/)
- [Kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation)
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [Helm](https://helm.sh/docs/intro/install/)
- Para desenvolvimento local: Python 3.12+ e [`uv`](https://docs.astral.sh/uv/)

## Container Image

```
ghcr.io/vinny1892/octantis:latest
```

Publicada automaticamente pelo CI a cada push no `master`. Para produção, pine por commit SHA (e.g., `ghcr.io/vinny1892/octantis:dba131d`).

## Setup — Kind Dev Cluster (recomendado)

O Octantis roda dentro de um cluster Kubernetes. O jeito mais rápido de testar é com o ambiente de dev incluso, que sobe um cluster Kind com stack de observabilidade completa:

- Prometheus + Grafana + Alertmanager (kube-prometheus-stack)
- Mimir (TSDB de longo prazo)
- OpenTelemetry Collector
- MetalLB (LoadBalancer)
- Grafana MCP (`ghcr.io/vinny1892/mcp-grafana:latest`)
- Kubernetes MCP (`ghcr.io/containers/kubernetes-mcp-server:latest`)
- Octantis (`ghcr.io/vinny1892/octantis:latest`)

```bash
# 1. Configurar secrets (escolha uma opção)

# Opção A: variáveis de ambiente
export OPENROUTER_API_KEY="sk-or-..."
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."

# Opção B: 1Password CLI (uma vez por máquina)
bash dev/op-setup.sh

# 2. Subir o cluster (~5 min)
bash dev/setup.sh

# Para recriar do zero
bash dev/setup.sh --force
```

| Serviço | URL | Credenciais |
|---|---|---|
| Grafana | http://grafana.octantis.cluster.local | admin / admin |
| Mimir API | http://mimir.octantis.cluster.local | — |
| nginx-demo | http://demo.octantis.cluster.local | — |

O `setup.sh` configura o DNS local automaticamente (MetalLB IP → `/etc/hosts`).

Ver [`dev/README.md`](../dev/README.md) para detalhes completos (arquitetura, troubleshooting, secrets).

## Deploy em Cluster Existente

Para deploy em um cluster Kubernetes que já existe (EKS, GKE, AKS, etc.), use os manifests de exemplo:

```bash
# 1. Criar namespace e secrets
kubectl create namespace monitoring
kubectl create secret generic octantis-secrets \
  --namespace monitoring \
  --from-literal=ANTHROPIC_API_KEY=sk-ant-... \
  --from-literal=GRAFANA_MCP_API_KEY=glsa_...

# 2. Deploy MCP servers + Octantis
kubectl apply -f examples/kubernetes/
```

Os manifests em [`examples/kubernetes/`](../examples/kubernetes/) incluem:

| Manifesto | Descrição | Imagem |
|---|---|---|
| `octantis.yaml` | Deployment + Service + ConfigMap | `ghcr.io/vinny1892/octantis:latest` |
| `mcp-grafana.yaml` | Grafana MCP Server | `ghcr.io/vinny1892/mcp-grafana:latest` |
| `mcp-k8s.yaml` | Kubernetes MCP Server (read-only) | `ghcr.io/containers/kubernetes-mcp-server:latest` |

Customize o ConfigMap em `octantis.yaml` para ajustar provider, modelo, notificações, etc.

### Exemplo com Bedrock

```yaml
# No ConfigMap do octantis.yaml
LLM_PROVIDER: "bedrock"
LLM_MODEL: "global.anthropic.claude-opus-4-6-v1"
# AWS_REGION_NAME via env var ou IAM role (IRSA no EKS)
```

## Desenvolvimento Local

Para rodar o Octantis fora do cluster (desenvolvimento de código):

```bash
# 1. Instale as dependências
uv sync

# 2. Configure o ambiente
cp .env.example .env
# Edite .env com suas chaves
```

Configuração mínima:

```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Grafana MCP (precisa de um mcp-grafana rodando — pode ser no Kind cluster)
GRAFANA_MCP_URL=http://localhost:8080/sse
GRAFANA_MCP_API_KEY=glsa_...

LOG_LEVEL=DEBUG

# Desabilitar notificações durante dev
SLACK_WEBHOOK_URL=
DISCORD_WEBHOOK_URL=
```

```bash
uv run octantis
```

Saída esperada:

```
{"version":"0.2.0","event":"octantis.starting"}
{"server":"grafana","tool_count":34,"event":"mcp.connected"}
{"grpc_port":4317,"http_port":4318,"event":"octantis.ready"}
```

**Nota:** O Octantis depende de MCP servers para investigação. Sem Grafana MCP, ele opera em modo degradado (analisa só com dados do trigger). Sem Kubernetes MCP, perde contexto de pods/events mas funciona normalmente.

## Enviando um Evento de Teste

Use `curl` para enviar um evento OTLP/HTTP diretamente ao Octantis:

```bash
# Evento com CPU alta — deve disparar investigação MCP
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

No Kind cluster, os eventos reais já fluem automaticamente — o OTel Collector scrapa kube-state-metrics a cada 30s e encaminha para o Octantis.

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
-> `src/octantis/pipeline/trigger_filter.py` — adicione/modifique regras
-> `src/octantis/pipeline/cooldown.py:21` — ajuste o fingerprint
-> `.env` — `PIPELINE_*` para tunar sem alterar código

### "Quero mudar como o LLM investiga os eventos"
-> `src/octantis/graph/nodes/investigator.py:28` — `INVESTIGATION_SYSTEM_PROMPT`
-> `src/octantis/mcp_client/manager.py` — conexão MCP e descoberta de ferramentas
-> `.env` — `INVESTIGATION_*` para ajustar budget e timeouts

### "Quero mudar como o LLM classifica os eventos"
-> `src/octantis/graph/nodes/analyzer.py:14` — `SYSTEM_PROMPT`
-> `src/octantis/models/analysis.py` — adicione campos ao `SeverityAnalysis`

### "Quero mudar o plano de ação gerado"
-> `src/octantis/graph/nodes/planner.py:14` — `SYSTEM_PROMPT`
-> `src/octantis/models/action_plan.py` — adicione `StepType` ou campos

### "Quero adicionar um canal de notificação"
-> Crie `src/octantis/notifiers/pagerduty.py` implementando `.send(investigation, analysis, action_plan)`
-> Instancie e chame em `src/octantis/graph/nodes/notifier.py`
-> Adicione settings em `src/octantis/config.py`

### "Quero adicionar métricas internas"
-> `src/octantis/metrics.py` — defina novos Counters/Histograms
-> Instrumente nos nós relevantes

### "Quero entender o formato OTLP"
-> `src/octantis/receivers/parser.py` — OTLP Protobuf/JSON -> InfraEvent
-> Os campos `resourceMetrics` e `resourceLogs` seguem o schema OTLP/JSON

---

## Variáveis de Ambiente — Referência Completa

| Variável | Default | Descrição |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG / INFO / WARNING / ERROR` |
| `MIN_SEVERITY_TO_NOTIFY` | `MODERATE` | Severidade mínima para acionar Slack/Discord |
| `LANGUAGE` | `en` | Idioma dos outputs do LLM (`en`, `pt-br`) |
| `LLM_PROVIDER` | `anthropic` | `anthropic`, `openrouter` ou `bedrock` |
| `LLM_MODEL` | `claude-sonnet-4-6` | Model ID para analyzer e planner |
| `LLM_INVESTIGATION_MODEL` | (= LLM_MODEL) | Model ID para investigator (opcional) |
| `ANTHROPIC_API_KEY` | — | Chave Anthropic (obrigatória se provider=anthropic) |
| `OPENROUTER_API_KEY` | — | Chave OpenRouter (obrigatória se provider=openrouter) |
| `AWS_REGION_NAME` | — | Região AWS (obrigatória se provider=bedrock). Credenciais via chain padrão AWS |
| `GRAFANA_MCP_URL` | — | URL SSE do Grafana MCP (obrigatório) |
| `GRAFANA_MCP_API_KEY` | — | API key do Grafana service account |
| `K8S_MCP_URL` | — | URL SSE do K8s MCP (recomendado). Imagem: `ghcr.io/containers/kubernetes-mcp-server:latest` |
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
