#!/bin/sh
CONFIG="${CONFIG_FILEPATH:-/config/console-config.yml}"
CONSOLE_BIN=""

for candidate in /app/console /console /usr/bin/console; do
  if [ -x "$candidate" ]; then
    CONSOLE_BIN="$candidate"
    break
  fi
done

if [ -z "$CONSOLE_BIN" ]; then
  CONSOLE_BIN="$(command -v console 2>/dev/null || true)"
fi

if [ -z "$CONSOLE_BIN" ] || [ ! -x "$CONSOLE_BIN" ]; then
  echo "redpanda console binary not found" >&2
  exit 1
fi

mkdir -p "$(dirname "$CONFIG")"

if [ ! -f "$CONFIG" ]; then
  cat >"$CONFIG" <<'EOF'
kafka:
  brokers:
    - "host.docker.internal:9092"
  sasl:
    enabled: false
  tls:
    enabled: false
  startup:
    establishConnectionEagerly: false
    maxRetries: 5
    retryInterval: 2s
    maxRetryInterval: 30s
    backoffMultiplier: 2
redpanda:
  adminApi:
    enabled: false
EOF
fi

LAST_HASH=""
CHILD_PID=""

stop_child() {
  if [ -n "$CHILD_PID" ] && kill -0 "$CHILD_PID" 2>/dev/null; then
    kill "$CHILD_PID" 2>/dev/null || true
    wait "$CHILD_PID" 2>/dev/null || true
  fi
  CHILD_PID=""
}

trap 'stop_child; exit 0' INT TERM

while true; do
  HASH="$(md5sum "$CONFIG" 2>/dev/null | awk '{print $1}' || echo "")"
  if [ "$HASH" != "$LAST_HASH" ]; then
    stop_child
    "$CONSOLE_BIN" -config.filepath="$CONFIG" &
    CHILD_PID=$!
    LAST_HASH="$HASH"
  fi

  if [ -n "$CHILD_PID" ] && ! kill -0 "$CHILD_PID" 2>/dev/null; then
    wait "$CHILD_PID" 2>/dev/null || true
    CHILD_PID=""
    LAST_HASH=""
  fi

  sleep 2
done
