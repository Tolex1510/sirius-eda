#!/usr/bin/env bash
# HTTPS только для платёжного webhook. Сайт и остальные API снаружи возвращают 404.
# SIRIUS_PROJECT=sirius-eda SIRIUS_ENV_FILE=.env scripts/webhook_tunnel.sh [локальный порт]
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
WEBHOOK_LOCAL_PORT=${1:-8082}
if [[ ! "$WEBHOOK_LOCAL_PORT" =~ ^[0-9]+$ ]]; then
  echo "Ожидается номер локального порта" >&2
  exit 1
fi
WEBHOOK_PORT="$WEBHOOK_LOCAL_PORT" docker compose \
  --env-file "${SIRIUS_ENV_FILE:-.env}" -p "${SIRIUS_PROJECT:-sirius-eda}" \
  --profile webhooks up -d --wait webhook-proxy
# Отдельный known_hosts и отсутствие ключей/агента: стороннему сервису не передаются ваши SSH-ключи.
exec ssh -F /dev/null -T -o BatchMode=yes -o ConnectTimeout=10 \
  -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=2 \
  -o StrictHostKeyChecking=accept-new \
  -o "UserKnownHostsFile=${TMPDIR:-/tmp}/sirius-localhost-run-known-hosts" \
  -o IdentityAgent=none -o IdentityFile=none \
  -R "80:127.0.0.1:$WEBHOOK_LOCAL_PORT" nokey@localhost.run
