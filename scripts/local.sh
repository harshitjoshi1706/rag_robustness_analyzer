#!/bin/sh
# No cloud deployment or registry publishing.
set -eu
case "${1:-start}" in
  start)
    count="${2:-1}"
    case "$count" in 1|2|4) ;; *) echo 'Worker count must be 1, 2 or 4' >&2; exit 2;; esac
    docker compose up -d --build --scale "worker=$count"
    ;;
  stop) docker compose stop ;;
  status) docker compose ps ;;
  logs) docker compose logs --tail 100 -f ;;
  *) echo 'Usage: scripts/local.sh start [1|2|4] | stop | status | logs' >&2; exit 2 ;;
esac
