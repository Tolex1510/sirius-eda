#!/bin/sh
set -u
# В туннель не передаются пользовательские ключи и агент. Known hosts хранится внутри контейнера.
while true; do
    ssh -F /dev/null -T -o BatchMode=yes -o ConnectTimeout=15 \
        -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=2 \
        -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/tmp/known_hosts \
        -o IdentityAgent=none -o IdentityFile=none \
        -R 80:webhook-proxy:80 nokey@localhost.run -- --output json
    echo 'Webhook tunnel disconnected; reconnecting in 5 seconds' >&2
    sleep 5
done
