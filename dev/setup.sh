#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CLUSTER_NAME="octantis-dev"
FORCE=false

# -----------------------------------------------
# Parse flags
# -----------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force|-f)
      FORCE=true
      shift
      ;;
    *)
      echo "Uso: bash dev/setup.sh [--force|-f]"
      echo ""
      echo "  --force, -f   Destrói o cluster existente e recria do zero"
      exit 1
      ;;
  esac
done

echo "============================================"
echo "  Octantis Dev Environment Setup"
echo "============================================"
echo ""

# -----------------------------------------------
# Verificar se o cluster já existe
# -----------------------------------------------
if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
  if [ "$FORCE" = true ]; then
    echo "==> Cluster '$CLUSTER_NAME' encontrado. Recriando (--force)..."
    bash "$SCRIPT_DIR/teardown.sh"
    echo ""
  else
    echo "==> Cluster '$CLUSTER_NAME' já está rodando."
    echo "  Use --force para destruir e recriar do zero."
    echo ""
    echo "  bash dev/setup.sh --force"
    exit 0
  fi
fi

# -----------------------------------------------
# 1. Kind cluster
# -----------------------------------------------
echo "==> [1/5] Criando diretórios de dados para Kind workers..."
mkdir -p /tmp/octantis-dev/worker1 /tmp/octantis-dev/worker2

echo "==> [1/5] Criando cluster Kind..."
kind create cluster --config "$SCRIPT_DIR/kind/kind-config.yaml"

echo "==> [1/5] Exportando kubeconfig..."
KUBECONFIG_PATH="$PROJECT_DIR/tmp/kubeconfig.yaml"
mkdir -p "$(dirname "$KUBECONFIG_PATH")"
kind get kubeconfig --name "$CLUSTER_NAME" > "$KUBECONFIG_PATH"
export KUBECONFIG="$KUBECONFIG_PATH"
echo "  KUBECONFIG=$KUBECONFIG_PATH"

# -----------------------------------------------
# 2. Helm repos
# -----------------------------------------------
echo "==> [2/5] Adicionando repositórios Helm..."
helm repo add grafana https://grafana.github.io/helm-charts 2>/dev/null || true
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>/dev/null || true
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts 2>/dev/null || true
helm repo update

# -----------------------------------------------
# 3. Gateway API (nginx-gateway-fabric)
# -----------------------------------------------
echo "==> [3/5] Instalando Gateway API CRDs..."
kubectl kustomize "https://github.com/nginx/nginx-gateway-fabric/config/crd/gateway-api/standard?ref=v2.5.0" | kubectl apply -f -

echo "==> [3/5] Instalando nginx-gateway-fabric (namespace: nginx-gateway)..."
helm install ngf oci://ghcr.io/nginx/charts/nginx-gateway-fabric \
  --version 2.5.0 \
  --namespace nginx-gateway --create-namespace \
  -f "$SCRIPT_DIR/helm/nginx-gateway-fabric/values.yaml" \
  --wait --timeout 3m

# -----------------------------------------------
# 4. kube-prometheus-stack (Prometheus + Grafana)
# -----------------------------------------------
echo "==> [4/5] Instalando kube-prometheus-stack (namespace: monitoring)..."
helm install prom prometheus-community/kube-prometheus-stack \
  --version 82.17.1 \
  --namespace monitoring --create-namespace \
  -f "$SCRIPT_DIR/helm/kube-prometheus-stack/values.yaml" \
  --wait --timeout 5m

# -----------------------------------------------
# 5. Mimir (TSDB) + Namespace + Gateway + Routes
# -----------------------------------------------
echo "==> [5/5] Criando namespace e Gateway resource..."
kubectl create namespace octantis --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "$SCRIPT_DIR/manifests/gateway.yaml"

echo "==> [5/5] Instalando Mimir (namespace: mimir)..."
helm install mimir grafana/mimir-distributed \
  --version 6.0.2 \
  --namespace mimir --create-namespace \
  -f "$SCRIPT_DIR/helm/mimir/values.yaml" \
  --wait --timeout 5m

# -----------------------------------------------
# Routes + ServiceMonitors
# -----------------------------------------------
echo ""
echo "==> Applying ServiceMonitors..."
for f in "$SCRIPT_DIR"/manifests/*-servicemonitor.yaml; do
  [ -f "$f" ] && kubectl apply -f "$f" 2>/dev/null || true
done

echo ""
echo "==> Criando routes de infra..."
kubectl apply -f "$SCRIPT_DIR/manifests/grafana-route.yaml"
kubectl apply -f "$SCRIPT_DIR/manifests/mimir-route.yaml"

echo ""
echo "==> Aplicando nginx-demo (teste de conectividade)..."
kubectl apply -f "$SCRIPT_DIR/manifests/nginx-demo.yaml"

# -----------------------------------------------
# Grafana MCP Server
# -----------------------------------------------
echo ""
echo "==> Criando service account token do Grafana para MCP..."
GRAFANA_URL="http://prom-grafana.monitoring.svc.cluster.local:80"

# Aguarda Grafana estar pronto
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=grafana -n monitoring --timeout=120s

# Cria service account + token via Grafana API (usando port-forward)
kubectl port-forward svc/prom-grafana 3001:80 -n monitoring &
PF_PID=$!
sleep 3

# Cria service account
SA_ID=$(curl -sf -X POST http://localhost:3001/api/serviceaccounts \
  -H "Content-Type: application/json" \
  -u admin:admin \
  -d '{"name":"mcp-grafana","role":"Viewer"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)

if [ -n "$SA_ID" ]; then
  # Gera token
  TOKEN=$(curl -sf -X POST "http://localhost:3001/api/serviceaccounts/$SA_ID/tokens" \
    -H "Content-Type: application/json" \
    -u admin:admin \
    -d '{"name":"mcp-token"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('key',''))" 2>/dev/null)
  echo "  Service account criada (id=$SA_ID)"
else
  # Service account já existe — gera token na existente
  SA_ID=$(curl -sf http://localhost:3001/api/serviceaccounts/search?query=mcp-grafana \
    -u admin:admin | python3 -c "import sys,json; print(json.load(sys.stdin)['serviceAccounts'][0]['id'])" 2>/dev/null)
  TOKEN=$(curl -sf -X POST "http://localhost:3001/api/serviceaccounts/$SA_ID/tokens" \
    -H "Content-Type: application/json" \
    -u admin:admin \
    -d '{"name":"mcp-token-'$(date +%s)'"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('key',''))" 2>/dev/null)
  echo "  Service account já existia (id=$SA_ID), novo token gerado"
fi

kill $PF_PID 2>/dev/null || true
wait $PF_PID 2>/dev/null || true

if [ -n "$TOKEN" ]; then
  # Cria secret com o token
  kubectl create secret generic mcp-grafana-token \
    --namespace monitoring \
    --from-literal=token="$TOKEN" \
    --dry-run=client -o yaml | kubectl apply -f -
  echo "  Secret mcp-grafana-token criado"

  # Deploy mcp-grafana
  echo "==> Instalando Grafana MCP Server (namespace: monitoring)..."
  kubectl apply -f "$SCRIPT_DIR/manifests/mcp-grafana.yaml"
else
  echo "  ⚠ Falha ao gerar token — MCP Grafana não será instalado"
  echo "  Crie manualmente: kubectl create secret generic mcp-grafana-token --namespace monitoring --from-literal=token=<TOKEN>"
fi

# -----------------------------------------------
# Octantis agent
# -----------------------------------------------
echo ""
echo "==> Carregando secrets do Octantis..."

# Suporte a 1Password (op) ou variáveis de ambiente.
# Se as variáveis já estiverem definidas no shell, usa elas.
# Senão, tenta ler do 1Password.
if [ -n "${OPENROUTER_API_KEY:-}" ] && [ -n "${SLACK_WEBHOOK_URL:-}" ] && [ -n "${DISCORD_WEBHOOK_URL:-}" ]; then
  echo "  Usando variáveis de ambiente"
elif command -v op &>/dev/null && op vault get Local &>/dev/null 2>&1; then
  echo "  Lendo do 1Password (vault: Local, item: octantis-dev)..."
  OPENROUTER_API_KEY=$(op read "op://Local/octantis-dev/OPENROUTER_API_KEY")
  SLACK_WEBHOOK_URL=$(op read "op://Local/octantis-dev/SLACK_WEBHOOK_URL")
  DISCORD_WEBHOOK_URL=$(op read "op://Local/octantis-dev/DISCORD_WEBHOOK_URL")
else
  echo "  ✗ Secrets não encontrados."
  echo "  Configure via variáveis de ambiente ou 1Password CLI."
  echo ""
  echo "  Opção 1 — Variáveis de ambiente:"
  echo "    export OPENROUTER_API_KEY=sk-or-..."
  echo "    export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/..."
  echo "    export DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/..."
  echo ""
  echo "  Opção 2 — 1Password CLI:"
  echo "    bash dev/op-setup.sh"
  echo "    eval \$(op signin)"
  exit 1
fi

kubectl create secret generic octantis-secrets \
  --namespace monitoring \
  --from-literal=OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
  --from-literal=SLACK_WEBHOOK_URL="$SLACK_WEBHOOK_URL" \
  --from-literal=DISCORD_WEBHOOK_URL="$DISCORD_WEBHOOK_URL" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "  Secret octantis-secrets criado"

echo "==> Instalando Octantis (namespace: monitoring)..."
kubectl apply -f "$SCRIPT_DIR/manifests/octantis.yaml"

echo ""
echo "============================================"
echo "  Ambiente pronto!"
echo "============================================"
echo ""
echo "  http://grafana.octantis.cluster.local     Grafana (admin/admin)"
echo "  http://mimir.octantis.cluster.local       Mimir (API)"
echo "  http://demo.octantis.cluster.local        nginx-demo (teste)"
echo ""
echo "  Octantis OTLP:  octantis.monitoring.svc.cluster.local:4317 (gRPC) / :4318 (HTTP)"
echo "  MCP Grafana:     mcp-grafana.monitoring.svc.cluster.local:8080"
echo ""
