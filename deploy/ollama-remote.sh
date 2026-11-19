#!/bin/sh
set -eu
# Only a public key and known_hosts are mounted; signing happens in the host agent.
while true; do
    ssh -F /dev/null -T -i /run/ollama-ssh/id.pub -o IdentitiesOnly=yes \
        -o BatchMode=yes -o StrictHostKeyChecking=yes \
        -o UserKnownHostsFile=/run/ollama-ssh/known_hosts -o ConnectTimeout=8 \
        -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
        -N -L 0.0.0.0:11434:127.0.0.1:11434 "${OLLAMA_SSH_USER}@${OLLAMA_SSH_HOST}" || true
    echo 'Ollama SSH connection closed; reconnecting in 5 seconds' >&2
    sleep 5
done
