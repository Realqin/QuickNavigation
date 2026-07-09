#!/usr/bin/env bash
# 在部署服务器上执行（由 Jenkins SSH 调用，也可手工执行）
set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-/opt/hlx/QuickNavigation}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-quicknav}"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.offline.yml -f docker-compose.prod.yml"
KAFKA_CONSOLE_PROVIDER="${KAFKA_CONSOLE_PROVIDER:-kafka-ui}"
FULL_REBUILD="${FULL_REBUILD:-0}"

cd "$DEPLOY_DIR"

if [[ ! -f .env ]]; then
  echo "缺少 $DEPLOY_DIR/.env，请先根据 .env.production.example 创建" >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

export COMPOSE_PROJECT_NAME
export KAFKA_CONSOLE_PROVIDER="${KAFKA_CONSOLE_PROVIDER:-kafka-ui}"

compose() {
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose $COMPOSE_FILES "$@"
  else
    docker compose $COMPOSE_FILES "$@"
  fi
}

echo "==> 同步后的代码目录: $DEPLOY_DIR"
echo "==> Kafka 控制台: $KAFKA_CONSOLE_PROVIDER"

if [[ "$FULL_REBUILD" == "1" ]]; then
  echo "==> 全量构建并启动（镜像变更、Dockerfile 变更时使用）"
  compose build backend frontend
  compose up -d
else
  echo "==> 常规发布：热更新前端 + 重启后端"
  if [[ ! -d frontend/dist ]]; then
    echo "缺少 frontend/dist，请确认 Jenkins 已构建前端" >&2
    exit 1
  fi

  if ! docker ps --format '{{.Names}}' | grep -qx 'quicknav-frontend'; then
    echo "quicknav-frontend 未运行，改为 compose up"
    compose up -d frontend backend
  else
    docker cp frontend/dist/. quicknav-frontend:/usr/share/nginx/html/
    if [[ "$KAFKA_CONSOLE_PROVIDER" == "kafka-ui" ]]; then
      docker cp frontend/nginx.kafka-ui.conf quicknav-frontend:/etc/nginx/conf.d/default.conf
    else
      docker cp frontend/nginx.redpanda.conf quicknav-frontend:/etc/nginx/conf.d/default.conf
    fi
    docker exec quicknav-frontend nginx -t
    docker exec quicknav-frontend nginx -s reload
  fi

  if docker ps --format '{{.Names}}' | grep -qx 'quicknav-backend'; then
    compose restart backend
  else
    compose up -d backend
  fi
fi

echo "==> 容器状态"
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'quicknav-|NAMES' || true

echo "==> 健康检查"
wget -q -S -O /dev/null http://127.0.0.1:8080 2>&1 | head -3 || true
wget -q -S -O /dev/null http://127.0.0.1:8000/docs 2>&1 | head -3 || true

echo "DEPLOY_OK"
