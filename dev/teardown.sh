#!/usr/bin/env bash
set -euo pipefail

echo "==> Deletando cluster Kind..."
kind delete cluster --name octantis-dev

echo "==> Limpando diretórios de dados..."
rm -rf /tmp/octantis-dev

echo "==> Ambiente removido."
