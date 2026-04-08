#!/usr/bin/env bash
set -euo pipefail

# Domínios *.octantis.cluster.local resolvendo para o IP do LoadBalancer (MetalLB)
# Adiciona entradas no /etc/hosts (requer sudo)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
KUBECONFIG_PATH="$PROJECT_DIR/tmp/kubeconfig.yaml"

DOMAINS=(
  "demo.octantis.cluster.local"
  "grafana.octantis.cluster.local"
  "mimir.octantis.cluster.local"
)

MARKER="# octantis-dev"

# Detect Gateway LoadBalancer IP
if [ -f "$KUBECONFIG_PATH" ]; then
  export KUBECONFIG="$KUBECONFIG_PATH"
  LB_IP=$(kubectl get svc -n nginx-gateway ngf-nginx-gateway-fabric -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)
fi

if [ -z "${LB_IP:-}" ]; then
  echo "⚠ LoadBalancer IP não encontrado. O cluster está rodando?"
  echo "  Execute 'bash dev/setup.sh' primeiro."
  echo ""
  echo "  Tentando usar 127.0.0.1 como fallback..."
  LB_IP="127.0.0.1"
fi

echo "==> Configurando DNS local para *.octantis.cluster.local → $LB_IP"

# Remove entradas anteriores
sudo sed -i "/$MARKER/d" /etc/hosts

# Adiciona novas entradas
for domain in "${DOMAINS[@]}"; do
  echo "$LB_IP $domain $MARKER" | sudo tee -a /etc/hosts > /dev/null
  echo "  + $domain → $LB_IP"
done

echo ""
echo "==> DNS configurado! Teste:"
echo "  curl http://demo.octantis.cluster.local"
