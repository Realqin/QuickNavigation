#!/bin/sh
set -eu

CONFIG="${KAFKA_UI_CONFIG_PATH:-/config/application.yml}"
CONSOLE_BIN=""

for candidate in /app/kafka-ui-api.jar /kafka-ui-api.jar; do
  if [ -f "$candidate" ]; then
    CONSOLE_BIN="$candidate"
    break
  fi
done

if [ -z "$CONSOLE_BIN" ]; then
  CONSOLE_BIN="$(find / -name 'kafka-ui-api.jar' 2>/dev/null | head -1 || true)"
fi

if [ -z "$CONSOLE_BIN" ] || [ ! -f "$CONSOLE_BIN" ]; then
  echo "kafka-ui jar not found" >&2
  exit 1
fi

mkdir -p "$(dirname "$CONFIG")"

if [ ! -f "$CONFIG" ]; then
  cat >"$CONFIG" <<'EOF'
kafka:
  clusters:
    - name: quicknav
      bootstrapServers: host.docker.internal:9092
      properties:
        security.protocol: PLAINTEXT
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
    java -jar "$CONSOLE_BIN" &
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
