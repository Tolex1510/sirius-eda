#!/usr/bin/env bash
# Manage the reconnecting Docker SSH tunnel to Hoshi's existing Ollama.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
case ${1:-status} in
  start)
    : "${SSH_AUTH_SOCK:?Unlock the SSH key and export SSH_AUTH_SOCK first}"
    ssh-add -l >/dev/null
    mkdir -p .local/ollama-ssh
    cp "${OLLAMA_SSH_KEY:-$HOME/.ssh/hoshi_pc}.pub" .local/ollama-ssh/id.pub
    cp "${OLLAMA_SSH_KNOWN_HOSTS:-$HOME/.ssh/known_hosts}" .local/ollama-ssh/known_hosts
    export OLLAMA_SSH_AGENT="$SSH_AUTH_SOCK"
    python3 - <<'PY'
import os,re
from pathlib import Path
p=Path('.env');s=p.read_text();key='OLLAMA_SSH_AGENT';value=os.environ[key]
if re.search('^'+key+'=',s,re.M):s=re.sub('^'+key+'=.*$',lambda _:key+'='+value,s,flags=re.M)
else:s+='\n'+key+'='+value+'\n'
p.write_text(s)
PY
    docker compose -p sirius-eda --profile remote-ai up -d --build --no-deps ollama-remote
    ;;
  stop) docker compose -p sirius-eda --profile remote-ai stop ollama-remote ;;
  status) docker compose -p sirius-eda --profile remote-ai ps ollama-remote ;;
  *) echo "Usage: $0 start|stop|status"; exit 2;;
esac
