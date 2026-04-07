#!/usr/bin/env bash
set -euo pipefail

# Domínios *.octantis.local resolvendo para 127.0.0.1
# Adiciona entradas no /etc/hosts (requer sudo)

DOMAINS=(
  "demo.octantis.cluster.local"
  "grafana.octantis.cluster.local"
  "mimir.octantis.cluster.local"
)

MARKER="# octantis-dev"

echo "==> Configurando DNS local para *.octantis.cluster.local..."

# Remove entradas anteriores
sudo sed -i "/$MARKER/d" /etc/hosts

# Adiciona novas entradas
for domain in "${DOMAINS[@]}"; do
  echo "127.0.0.1 $domain $MARKER" | sudo tee -a /etc/hosts > /dev/null
  echo "  + $domain → 127.0.0.1"
done

echo ""
echo "==> DNS configurado! Teste:"
echo "  curl http://demo.octantis.cluster.local"
