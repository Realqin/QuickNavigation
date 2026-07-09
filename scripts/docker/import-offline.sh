#!/usr/bin/env bash
# 在离线目标服务器上执行：导入镜像并启动
# 用法：bash scripts/docker/import-offline.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TAR_FILE="$ROOT/offline/docker-images/quicknav-images.tar"

if [[ ! -f "$TAR_FILE" ]]; then
  echo "未找到 $TAR_FILE ，请先从有网环境运行 export-offline.sh" >&2
  exit 1
fi

cd "$ROOT"
export COMPOSE_PROJECT_NAME=quicknav

echo "==> 导入镜像..."
docker load -i "$TAR_FILE"

echo "==> 离线启动（不拉取、不构建）..."
docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d --no-build

echo ""
echo "启动完成。访问 http://<服务器IP>:8080"
