#!/usr/bin/env bash
set -euo pipefail

# Remove entradas *.octantis.local do /etc/hosts
MARKER="# octantis-dev"

echo "==> Removendo entradas octantis-dev do /etc/hosts..."
sudo sed -i "/$MARKER/d" /etc/hosts
echo "==> Limpo."
