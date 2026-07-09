#!/bin/sh
set -eu

provider="${KAFKA_CONSOLE_PROVIDER:-redpanda}"
if [ "$provider" = "kafka-ui" ]; then
  cp /etc/nginx/conf.d/default.kafka-ui.conf /etc/nginx/conf.d/default.conf
else
  cp /etc/nginx/conf.d/default.redpanda.conf /etc/nginx/conf.d/default.conf
fi

exec /docker-entrypoint.sh "$@"
