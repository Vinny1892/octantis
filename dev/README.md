# Ambiente de Desenvolvimento

Cluster Kind local com stack de observabilidade completa para desenvolvimento e testes do Octantis.

## Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/)
- [Kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation)
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [Helm](https://helm.sh/docs/intro/install/)
- [1Password CLI](https://developer.1password.com/docs/cli/get-started/) (`op`) — *opcional, alternativa: variáveis de ambiente*

## Setup Rápido

```bash
# 1. Configurar DNS local (requer sudo)
sudo bash dev/dns-setup.sh

# 2. Configurar secrets (escolha uma opção)

# Opção A: variáveis de ambiente (sem 1Password)
export OPENROUTER_API_KEY="sk-or-..."
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."

# Opção B: 1Password (uma vez por máquina)
bash dev/op-setup.sh
# Edite os valores no 1Password com as chaves reais

# 3. Subir o cluster
bash dev/setup.sh

# Para recriar do zero (destrói e recria)
bash dev/setup.sh --force
```

## Arquitetura do Cluster

```mermaid
%%{init: {"theme": "dark", "themeVariables": {"primaryColor": "#2d333b", "primaryBorderColor": "#6d5dfc", "primaryTextColor": "#e6edf3", "lineColor": "#8b949e", "secondaryColor": "#161b22"}}}%%
flowchart TD
    subgraph kind["Kind Cluster (octantis-dev)"]
        subgraph ngw["nginx-gateway"]
            GW["nginx-gateway-fabric\n:80 LoadBalancer (MetalLB)"]:::infra
        end

        subgraph mon["monitoring"]
            PROM["Prometheus\n(kube-prometheus-stack)"]:::infra
            GRAF["Grafana\n(admin/admin)"]:::infra
            AM["Alertmanager"]:::infra
            MCP["mcp-grafana\n:8080/sse"]:::app
            MCPK8S["mcp-k8s\n:8080/sse"]:::app
            OCT["Octantis\n:4317 gRPC / :4318 HTTP\n:9090 metrics"]:::app
        end

        subgraph mir["mimir"]
            MIMIR["Mimir Distributed\n(gateway + ingester + compactor\n+ querier + store-gateway)"]:::infra
            MINIO["MinIO\n(object storage)"]:::infra
        end

        subgraph oct["octantis"]
            GWRES["Gateway resource\n(octantis-gateway)"]:::infra
            DEMO["nginx-demo\n(teste)"]:::infra
        end
    end

    HOST["Host"]:::ext
    MLB["MetalLB\n(L2 advertisement)"]:::infra

    HOST -->|"*.octantis.cluster.local"| MLB
    MLB --> GW
    GW -->|"grafana.octantis.cluster.local"| GRAF
    GW -->|"mimir.octantis.cluster.local"| MIMIR
    GW -->|"demo.octantis.cluster.local"| DEMO

    PROM -->|"remote_write"| MIMIR
    MIMIR --> MINIO
    GRAF -->|"datasource"| PROM
    GRAF -->|"datasource Mimir"| MIMIR
    MCP -->|"Grafana API"| GRAF
    OCT -->|"MCP SSE"| MCP
    OCT -->|"MCP SSE"| MCPK8S
    PROM -->|"scrape :9090"| OCT

    classDef ext fill:#1c2128,stroke:#6d5dfc,color:#e6edf3
    classDef infra fill:#2d333b,stroke:#30363d,color:#e6edf3
    classDef app fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
```

## Componentes

### Kind Cluster (`dev/kind/kind-config.yaml`)

Cluster com 1 control-plane + 2 workers. Workers montam `/tmp/octantis-dev/worker{1,2}` como `/data` para persistent volumes.

### MetalLB

LoadBalancer para Kind. Instalado via Helm no namespace `metallb-system`. O `setup.sh` detecta automaticamente a subnet Docker do Kind e aloca um range `/28` (e.g., `172.18.255.200-172.18.255.250`) para IPs de LoadBalancer.

Isso permite usar `type: LoadBalancer` nos Services ao invés de NodePort.

### nginx-gateway-fabric (`dev/helm/nginx-gateway-fabric/values.yaml`)

Gateway API implementation via NGINX. Substitui ingress-nginx tradicional. O service `ngf-nginx-gateway-fabric` é do tipo LoadBalancer — o MetalLB atribui um IP acessível da máquina host.

O Gateway resource (`dev/manifests/gateway.yaml`) aceita HTTPRoutes de todos os namespaces.

### kube-prometheus-stack (`dev/helm/kube-prometheus-stack/values.yaml`)

Stack completa de monitoramento no namespace `monitoring`:

| Componente | Configuração |
|------------|-------------|
| **Prometheus** | Scrape 30s, retention 2h/2GB, remote_write para Mimir |
| **Grafana** | admin/admin, anonymous viewer, datasources Prometheus + Mimir |
| **Alertmanager** | Habilitado, receiver null (sem notificações) |
| **node-exporter** | Métricas do host |
| **kube-state-metrics** | Métricas do cluster |

Prometheus faz remote_write para Mimir com header `X-Scope-OrgID: dev` para retenção de longo prazo. Retenção local é curta (2h) porque Mimir é o storage primário.

### Mimir (`dev/helm/mimir/values.yaml`)

TSDB distribuído para métricas de longo prazo, no namespace `mimir`. Multitenancy habilitado com tenant `dev`.

| Componente | Réplicas |
|------------|----------|
| distributor | 1 |
| ingester | 1 |
| querier | 1 |
| query-frontend | 1 |
| query-scheduler | 1 |
| store-gateway | 1 |
| compactor | 1 |
| nginx (gateway) | 1 |
| **MinIO** | 1 (object storage local) |

MinIO serve como S3-compatible storage para blocks, ruler e alertmanager. Credenciais: `mimir`/`supersecret`.

O datasource Mimir no Grafana aponta para `http://mimir-gateway.mimir.svc.cluster.local/prometheus` com header `X-Scope-OrgID: dev`.

### OpenTelemetry Collector (`dev/helm/opentelemetry-collector/values.yaml`)

Collector em modo deployment (1 réplica). Recebe OTLP gRPC (:4317) e HTTP (:4318).

| Pipeline | Receivers | Exporters |
|----------|-----------|-----------|
| metrics | otlp | prometheusremotewrite (Mimir), debug |
| traces | otlp | debug |
| logs | otlp | debug |

Métricas OTLP são convertidas e enviadas para Mimir via remote write. Traces e logs atualmente só vão para debug (stdout).

### Grafana MCP Server (`dev/manifests/mcp-grafana.yaml`)

Servidor MCP (Model Context Protocol) que expõe ferramentas de query do Grafana via SSE. Roda no namespace `monitoring`.

- **Imagem**: `ghcr.io/vinny1892/mcp-grafana:latest` (built from [grafana/mcp-grafana](https://github.com/grafana/mcp-grafana))
- **Endpoint**: `mcp-grafana.monitoring.svc.cluster.local:8080/sse` (Service :8080 → container :8000)
- **Autenticação**: Service account token do Grafana (`GRAFANA_SERVICE_ACCOUNT_TOKEN`), criado automaticamente pelo `setup.sh` e armazenado no secret `mcp-grafana-token`

### Kubernetes MCP Server (`dev/manifests/mcp-k8s.yaml`)

Servidor MCP que expõe queries de recursos Kubernetes via SSE. Roda no namespace `monitoring` com acesso read-only ao cluster.

- **Imagem**: `ghcr.io/containers/kubernetes-mcp-server:latest`
- **Endpoint**: `mcp-k8s.monitoring.svc.cluster.local:8080/sse`
- **Autenticação**: ServiceAccount `mcp-k8s` com ClusterRole read-only (pods, deployments, services, events, etc.)
- **Modo**: `--read-only` (não permite modificações no cluster)

### Octantis (`dev/manifests/octantis.yaml`)

O agente Octantis roda no namespace `monitoring`.

- **Imagem**: `ghcr.io/vinny1892/octantis:latest`
- **LLM**: OpenRouter (`claude-sonnet-4-6`)
- **MCP**: Conecta ao `mcp-grafana` e `mcp-k8s` via SSE
- **OTLP**: Recebe em `:4317` (gRPC) e `:4318` (HTTP)
- **Métricas**: Exporta em `:9090/metrics` (scrapeado pelo Prometheus)
- **Idioma**: `LANGUAGE=pt-br` (análises e notificações em português; default: `en`)
- **Secrets**: Via variáveis de ambiente ou 1Password (ver [Secrets](#secrets))

### nginx-demo (`dev/manifests/nginx-demo.yaml`)

Deployment simples de NGINX no namespace `octantis` para testar conectividade do Gateway. Acessível em `http://demo.octantis.cluster.local`.

## DNS Local (`dev/dns-setup.sh`)

Adiciona entradas no `/etc/hosts` para resolver os domínios do cluster, apontando para o IP do LoadBalancer (MetalLB):

| Domínio | Serviço |
|---------|---------|
| `grafana.octantis.cluster.local` | Grafana UI |
| `mimir.octantis.cluster.local` | Mimir API |
| `demo.octantis.cluster.local` | nginx-demo |

O `setup.sh` configura o DNS automaticamente. Se precisar reconfigurar manualmente:

```bash
sudo bash dev/dns-setup.sh
```

O tráfego chega no IP do MetalLB → nginx-gateway-fabric (LoadBalancer) → HTTPRoute → Service destino.

Para remover: `sudo bash dev/dns-cleanup.sh`

## Secrets

O Octantis precisa de 3 secrets para funcionar:

| Variável | Descrição |
|----------|-----------|
| `OPENROUTER_API_KEY` | Chave da API OpenRouter para o LLM |
| `SLACK_WEBHOOK_URL` | Incoming webhook do Slack para notificações |
| `DISCORD_WEBHOOK_URL` | Webhook do Discord para notificações |

O `setup.sh` aceita duas formas de fornecer essas secrets, com a seguinte prioridade:

1. **Variáveis de ambiente** — se já estiverem definidas no shell, são usadas diretamente
2. **1Password CLI** — se `op` estiver instalado e autenticado, lê do vault `Local`

### Opção 1: Variáveis de ambiente

Para quem não usa 1Password. Exporte as variáveis antes de rodar o setup:

```bash
export OPENROUTER_API_KEY="sk-or-..."
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."

bash dev/setup.sh
```

Ou em uma linha:

```bash
OPENROUTER_API_KEY="sk-or-..." \
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..." \
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..." \
bash dev/setup.sh
```

### Opção 2: 1Password CLI

Para quem usa 1Password. Configure uma vez por máquina:

```bash
# Cria o item com valores placeholder
bash dev/op-setup.sh

# Edite com os valores reais
op item edit octantis-dev --vault Local 'OPENROUTER_API_KEY=sk-or-...'
op item edit octantis-dev --vault Local 'SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...'
op item edit octantis-dev --vault Local 'DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...'
```

Nas execuções seguintes, o `setup.sh` lê automaticamente via `op read "op://Local/octantis-dev/..."`.

## ServiceMonitors

| Monitor | Namespace | Target |
|---------|-----------|--------|
| `nginx-gateway-fabric` | `nginx-gateway` | NGF metrics `:9113` |
| Octantis (via annotation) | `monitoring` | `:9090/metrics` |

## Scripts

| Script | Descrição |
|--------|-----------|
| `dev/setup.sh` | Sobe o cluster completo (Kind + Helm charts + manifests + secrets). Idempotente — se o cluster já existe, exibe aviso e sai |
| `dev/setup.sh --force` | Destrói o cluster existente e recria tudo do zero |
| `dev/teardown.sh` | Deleta o cluster Kind e limpa dados locais |
| `dev/dns-setup.sh` | Configura `/etc/hosts` com IP do LoadBalancer (requer sudo) |
| `dev/dns-cleanup.sh` | Remove entradas do `/etc/hosts` (requer sudo) |
| `dev/op-setup.sh` | Cria item `octantis-dev` no 1Password vault `Local` |

## Estrutura de Arquivos

```
dev/
├── setup.sh                              # Script principal de setup
├── teardown.sh                           # Destruir cluster
├── dns-setup.sh                          # DNS local (*.octantis.cluster.local)
├── dns-cleanup.sh                        # Limpar DNS local
├── op-setup.sh                           # Criar item no 1Password
├── kind/
│   └── kind-config.yaml                  # 1 control-plane + 2 workers, NodePort mappings
├── helm/
│   ├── kube-prometheus-stack/
│   │   └── values.yaml                   # Prometheus + Grafana + Alertmanager
│   ├── mimir/
│   │   └── values.yaml                   # Mimir distributed + MinIO
│   ├── nginx-gateway-fabric/
│   │   └── values.yaml                   # Gateway API controller (NodePort)
│   └── opentelemetry-collector/
│       └── values.yaml                   # OTel Collector → Mimir remote write
└── manifests/
    ├── gateway.yaml                      # Gateway resource (aceita HTTPRoutes de todos ns)
    ├── grafana-route.yaml                # HTTPRoute + ReferenceGrant para Grafana
    ├── mimir-route.yaml                  # HTTPRoute para Mimir API
    ├── metallb-config.yaml               # IPAddressPool + L2Advertisement (MetalLB)
    ├── mcp-grafana.yaml                  # Deployment + Service do MCP Grafana
    ├── mcp-k8s.yaml                      # ServiceAccount + RBAC + Deployment + Service do MCP K8s
    ├── octantis.yaml                     # Deployment + Service do Octantis
    ├── nginx-demo.yaml                   # Deployment + Service + HTTPRoute (teste)
    └── ngf-servicemonitor.yaml           # ServiceMonitor para nginx-gateway-fabric
```

## Troubleshooting

### Gateway retorna 404

O HTTPRoute pode não ter sido aceito. Verifique:

```bash
kubectl get httproute -A
kubectl describe httproute <nome> -n <namespace>
```

Se o status não tem `Accepted: True`, verifique se o ReferenceGrant existe (necessário para routes cross-namespace).

### Grafana MCP não conecta

```bash
kubectl logs -n monitoring deploy/mcp-grafana
kubectl get secret mcp-grafana-token -n monitoring -o jsonpath='{.data.token}' | base64 -d
```

Se o token estiver vazio, recrie via Grafana API ou re-execute o setup.

### Octantis em CrashLoopBackoff

```bash
kubectl logs -n monitoring deploy/octantis
kubectl get secret octantis-secrets -n monitoring -o yaml
```

Causas comuns: `OPENROUTER_API_KEY` com valor `change-me` (edite no 1Password), MCP Grafana não está rodando.

### DNS não resolve

```bash
grep octantis /etc/hosts
curl -H "Host: grafana.octantis.cluster.local" http://127.0.0.1
```

Se o curl funciona mas o browser não, o `/etc/hosts` pode não ter sido atualizado. Re-execute `sudo bash dev/dns-setup.sh`.
