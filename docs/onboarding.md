---
title: "Onboarding — Zero to Running"
description: "Como subir o Octantis localmente e contribuir com o código"
---

# Onboarding — Zero to Running

## Pré-requisitos

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) instalado
- Docker + Docker Compose (para Redpanda local)
- Acesso de leitura ao Prometheus e ao cluster K8s de staging (opcional para desenvolvimento)

## Setup em 5 minutos

```bash
# 1. Clone e entre no diretório
cd /home/vinny/repo/octantis

# 2. Instale as dependências (uv cria o venv automaticamente)
uv sync

# 3. Configure o ambiente
cp .env.example .env
# Edite .env com suas chaves (mínimo: ANTHROPIC_API_KEY)
```

Configuração mínima para rodar localmente sem K8s/Prometheus reais:

```env
# .env mínimo para desenvolvimento
ANTHROPIC_API_KEY=sk-ant-...
REDPANDA_BROKERS=localhost:9092
K8S_IN_CLUSTER=false
LOG_LEVEL=DEBUG

# Desabilitar notificações para não spammar Slack/Discord durante dev
# (deixar as vars em branco desabilita o notifier)
SLACK_WEBHOOK_URL=
DISCORD_WEBHOOK_URL=
```

## Subindo o Redpanda local

Crie um `docker-compose.yml` na raiz do projeto:

```yaml
version: "3.8"
services:
  redpanda:
    image: redpandadata/redpanda:latest
    command:
      - redpanda
      - start
      - --overprovisioned
      - --smp 1
      - --memory 512M
      - --reserve-memory 0M
      - --node-id 0
      - --check=false
      - --kafka-addr PLAINTEXT://0.0.0.0:9092
      - --advertise-kafka-addr PLAINTEXT://localhost:9092
    ports:
      - "9092:9092"
      - "9644:9644"
    healthcheck:
      test: ["CMD-SHELL", "rpk cluster health | grep -q 'Healthy: true'"]
      interval: 5s
      timeout: 5s
      retries: 10
```

```bash
docker compose up -d redpanda

# Criar o tópico
docker compose exec redpanda rpk topic create otel-infra-events
```

## Rodando o agente

```bash
uv run octantis
```

Saída esperada com `LOG_LEVEL=DEBUG`:

```
2026-03-23T13:00:00Z [info] octantis.starting version=0.1.0
2026-03-23T13:00:00Z [info] octantis.ready topic=otel-infra-events batch_window_s=30.0 sampler_cooldown_s=300.0
```

## Enviando um evento de teste

Publique um evento fake no Redpanda para ver o pipeline em ação:

```bash
# Evento com CPU alta — deve passar pelo PreFilter e chegar ao LLM
docker compose exec redpanda rpk topic produce otel-infra-events --key test << 'EOF'
{
  "event_id": "test-001",
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
}
EOF
```

```bash
# Evento benigno — deve ser dropado pelo PreFilter (HealthCheckRule)
docker compose exec redpanda rpk topic produce otel-infra-events --key test << 'EOF'
{
  "event_id": "test-002",
  "resourceLogs": [{
    "resource": {"attributes": [
      {"key": "service.name", "value": {"stringValue": "api-server"}}
    ]},
    "scopeLogs": [{"logRecords": [
      {"body": {"stringValue": "GET /healthz HTTP/1.1 200 OK"}, "severityText": "INFO"}
    ]}]
  }]
}
EOF
```

Com `LOG_LEVEL=DEBUG`, o segundo evento deve gerar:

```
[debug] prefilter.rule_matched rule=health_check decision=drop reason="health probe log: GET /healthz HTTP/1.1 200 OK"
```

## Rodando os testes

```bash
uv run pytest                     # todos os testes
uv run pytest tests/test_pipeline.py -v  # só pipeline
uv run pytest -k "prefilter" -v   # por nome
```

Todos os testes usam mocks — nenhuma chamada real ao LLM ou APIs externas.

---

## Mapa de Leitura do Código

Dependendo do que você quer entender ou modificar:

### "Quero ajustar o que passa para o LLM"
→ `src/octantis/pipeline/prefilter.py` — adicione/modifique regras
→ `src/octantis/pipeline/sampler.py:22` — ajuste o fingerprint
→ `.env` — `PIPELINE_*` para tunar sem alterar código

### "Quero mudar como o LLM classifica os eventos"
→ `src/octantis/graph/nodes/analyzer.py:14` — `SYSTEM_PROMPT`
→ `src/octantis/models/analysis.py` — adicione campos ao `SeverityAnalysis`

### "Quero mudar o plano de ação gerado"
→ `src/octantis/graph/nodes/planner.py:14` — `SYSTEM_PROMPT`
→ `src/octantis/models/action_plan.py` — adicione `StepType` ou campos

### "Quero adicionar um canal de notificação"
→ Crie `src/octantis/notifiers/pagerduty.py` implementando `.send(enriched_event, analysis, action_plan)`
→ Instancie e chame em `src/octantis/graph/nodes/notifier.py`
→ Adicione settings em `src/octantis/config.py`

### "Quero entender o formato de mensagem do Redpanda"
→ `src/octantis/consumers/redpanda.py:19` — `_parse_otel_message()`
→ Os campos `resourceMetrics` e `resourceLogs` seguem o schema OTLP/JSON

---

## Adicionando uma Nova Regra de Filtro

Exemplo: dropar eventos de namespaces de CI/CD que são sabidamente ruidosos.

**1. Implemente em `prefilter.py`:**

```python
@dataclass
class NamespaceBlocklistRule:
    name: str = "namespace_blocklist"
    blocked_namespaces: frozenset[str] = frozenset({"ci", "cd", "staging-ephemeral"})

    def evaluate(self, event: InfraEvent) -> FilterResult | None:
        ns = event.resource.k8s_namespace or ""
        if ns in self.blocked_namespaces:
            return FilterResult(
                decision=Decision.DROP,
                rule=self.name,
                reason=f"namespace '{ns}' is in blocklist",
            )
        return None
```

**2. Injete em `main.py`:**

```python
pre_filter = PreFilter(rules=[
    HealthCheckRule(),
    NamespaceBlocklistRule(blocked_namespaces=frozenset(cfg.blocked_namespaces_list)),
    BenignPatternRule(patterns=cfg.benign_patterns_list),
    # ... resto das regras
])
```

**3. Adicione o config em `config.py` e `.env.example`:**

```python
# PipelineSettings
blocked_namespaces: str = ""

@property
def blocked_namespaces_list(self) -> list[str]:
    return [n.strip() for n in self.blocked_namespaces.split(",") if n.strip()]
```

```env
PIPELINE_BLOCKED_NAMESPACES=ci,cd,staging-ephemeral
```

**4. Escreva o teste:**

```python
def test_namespace_blocklist_drops_ci():
    rule = NamespaceBlocklistRule()
    event = _event(ns="ci")
    assert rule.evaluate(event).decision == Decision.DROP

def test_namespace_blocklist_passes_production():
    rule = NamespaceBlocklistRule()
    event = _event(ns="production")
    assert rule.evaluate(event) is None
```

---

## Variáveis de Ambiente — Referência Completa

| Variável | Default | Descrição |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG / INFO / WARNING / ERROR` |
| `MIN_SEVERITY_TO_NOTIFY` | `MODERATE` | Severidade mínima para acionar Slack/Discord |
| `REDPANDA_BROKERS` | `localhost:9092` | Brokers separados por vírgula |
| `REDPANDA_TOPIC` | `otel-infra-events` | Tópico a consumir |
| `REDPANDA_GROUP_ID` | `octantis-agent` | Consumer group ID |
| `LLM_PROVIDER` | `anthropic` | `anthropic` ou `openrouter` |
| `LLM_MODEL` | `claude-sonnet-4-6` | Model ID |
| `ANTHROPIC_API_KEY` | — | Chave Anthropic (obrigatória se provider=anthropic) |
| `OPENROUTER_API_KEY` | — | Chave OpenRouter (obrigatória se provider=openrouter) |
| `PROMETHEUS_URL` | `http://prometheus:9090` | URL base do Prometheus |
| `K8S_IN_CLUSTER` | `false` | `true` quando rodando dentro do cluster |
| `SLACK_WEBHOOK_URL` | — | Incoming webhook URL (vazio = desabilitado) |
| `SLACK_BOT_TOKEN` | — | Bot token (alternativa ao webhook) |
| `SLACK_CHANNEL` | `#infra-alerts` | Channel (só usado com bot token) |
| `DISCORD_WEBHOOK_URL` | — | Webhook URL (vazio = desabilitado) |
| `PIPELINE_CPU_THRESHOLD` | `75.0` | % CPU para considerar anômalo |
| `PIPELINE_MEMORY_THRESHOLD` | `80.0` | % memória para considerar anômalo |
| `PIPELINE_ERROR_RATE_THRESHOLD` | `0.01` | req/s de erros para considerar anômalo |
| `PIPELINE_BENIGN_PATTERNS` | `""` | Regexes separados por vírgula para sempre dropar |
| `PIPELINE_ALLOWED_EVENT_TYPES` | `""` | Whitelist de tipos (vazio = todos) |
| `PIPELINE_BATCH_WINDOW_SECONDS` | `30.0` | Janela de agrupamento em segundos |
| `PIPELINE_BATCH_MAX_SIZE` | `20` | Máximo de eventos por batch antes do flush |
| `PIPELINE_SAMPLER_COOLDOWN_SECONDS` | `300` | Segundos de supressão por fingerprint |
| `PIPELINE_SAMPLER_MAX_ENTRIES` | `1000` | Máximo de fingerprints em memória |
