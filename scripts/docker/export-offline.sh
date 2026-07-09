#!/usr/bin/env bash
# 在有网络的机器上执行：拉取/构建全部镜像并导出为 tar
# 用法：bash scripts/docker/export-offline.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT_DIR="$ROOT/offline/docker-images"
TAR_FILE="$OUT_DIR/quicknav-images.tar"
MANIFEST="$OUT_DIR/images.txt"

mkdir -p "$OUT_DIR"
cd "$ROOT"

export COMPOSE_PROJECT_NAME=quicknav
export DOCKER_BUILDKIT=1

echo "==> 拉取 compose 中声明的远端镜像..."
docker compose pull mysql sshwifty-app redisinsight-app

echo "==> 预拉取 Dockerfile 基础镜像..."
BASE_IMAGES=(
  omnidbteam/omnidb:latest
  nginx:latest
  docker.redpanda.com/redpandadata/console:v2.8.0
  python:3.12-slim
  node:20-alpine
  nginx:1.27-alpine
)
for img in "${BASE_IMAGES[@]}"; do
  echo "    pull $img"
  docker pull "$img"
done

echo "==> 构建项目镜像..."
docker compose build

echo "==> 收集镜像列表..."
mapfile -t IMAGES < <(docker compose config --images | sort -u)
printf '%s\n' "${IMAGES[@]}" > "$MANIFEST"
echo "    共 ${#IMAGES[@]} 个镜像，清单: $MANIFEST"

echo "==> 导出到 $TAR_FILE ..."
rm -f "$TAR_FILE"
docker save -o "$TAR_FILE" "${IMAGES[@]}"

SIZE_MB=$(du -m "$TAR_FILE" | awk '{print $1}')
echo ""
echo "完成。请将以下文件拷贝到目标服务器："
echo "  - $TAR_FILE  (${SIZE_MB} MB)"
echo "  - $MANIFEST"
echo "  - 整个项目目录"
echo ""
echo "目标服务器导入："
echo "  bash scripts/docker/import-offline.sh"
