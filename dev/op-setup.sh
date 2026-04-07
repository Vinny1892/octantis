#!/usr/bin/env bash
set -euo pipefail

# Cria o item octantis-dev no 1Password para armazenar secrets do ambiente de dev.
# Execute uma vez por máquina/conta 1Password.
#
# Uso:
#   bash dev/op-setup.sh
#   # Depois edite os valores no 1Password app ou via CLI:
#   op item edit octantis-dev --vault Local 'OPENROUTER_API_KEY=sk-or-...'

VAULT="Local"
ITEM="octantis-dev"

echo "==> Verificando 1Password CLI..."
if ! command -v op &>/dev/null; then
  echo "  ✗ 1Password CLI (op) não encontrado"
  echo "  Instale: https://developer.1password.com/docs/cli/get-started/"
  exit 1
fi

echo "==> Verificando sessão 1Password..."
if ! op vault get "$VAULT" &>/dev/null; then
  echo "  ✗ Não foi possível acessar vault '$VAULT'. Execute: eval \$(op signin)"
  exit 1
fi

echo "==> Verificando se item '$ITEM' já existe..."
if op item get "$ITEM" --vault "$VAULT" &>/dev/null; then
  echo "  Item '$ITEM' já existe no vault '$VAULT'. Nada a fazer."
  echo "  Para ver: op item get $ITEM --vault $VAULT --reveal"
  exit 0
fi

echo "==> Criando item '$ITEM' no vault '$VAULT'..."
op item create \
  --vault "$VAULT" \
  --category "API Credential" \
  --title "$ITEM" \
  'OPENROUTER_API_KEY[password]=change-me' \
  'SLACK_WEBHOOK_URL[password]=change-me' \
  'DISCORD_WEBHOOK_URL[password]=change-me'

echo ""
echo "Item criado com valores placeholder (change-me)."
echo "Edite com os valores reais:"
echo "  op item edit $ITEM --vault $VAULT 'OPENROUTER_API_KEY=sk-or-...'"
echo "  op item edit $ITEM --vault $VAULT 'SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...'"
echo "  op item edit $ITEM --vault $VAULT 'DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...'"
