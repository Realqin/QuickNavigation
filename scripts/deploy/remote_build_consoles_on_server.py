#!/usr/bin/env python3
"""Upload ARM64 console sources and build/start directly on online server (192.168.6.189).

Does NOT build on local Windows or proxy consoles to 192.168.6.127.
Requires base images already loaded on server: python:3.12-slim-bookworm, provectuslabs/kafka-ui:v0.7.2
"""
from __future__ import annotations

import os
import sys

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "192.168.6.189")
USER = os.environ.get("DEPLOY_USER", "root")
PASSWORD = os.environ.get("DEPLOY_PASSWORD", "firefly")
PROJECT_DIR = os.environ.get("DEPLOY_PROJECT_DIR", "/opt/hlx/QuickNavigation")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def upload_tree(sftp: paramiko.SFTPClient, local_dir: str, remote_dir: str) -> None:
    for base, _, files in os.walk(local_dir):
        rel = os.path.relpath(base, local_dir).replace("\\", "/")
        remote_base = remote_dir if rel == "." else f"{remote_dir}/{rel}"
        try:
            sftp.stat(remote_base)
        except OSError:
            parts = remote_base.strip("/").split("/")
            cur = ""
            for part in parts:
                cur += f"/{part}"
                try:
                    sftp.stat(cur)
                except OSError:
                    sftp.mkdir(cur)
        for name in files:
            local_path = os.path.join(base, name)
            remote_path = f"{remote_base}/{name}"
            print(f"Upload {local_path} -> {remote_path}")
            sftp.put(local_path, remote_path)


def main() -> int:
    vendor_tar = os.path.join(ROOT, "docker", "omnidb", "vendor", "OmniDB-3.0.3b.tar.gz")
    has_local_vendor = os.path.isfile(vendor_tar) and os.path.getsize(vendor_tar) > 100_000
    if not has_local_vendor:
        print(
            "Note: local OmniDB vendor tarball not found; server build will use vendor/ on server or wget during docker build."
        )

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting {USER}@{HOST} ...")
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    sftp = ssh.open_sftp()

    upload_paths = [
        ("docker/omnidb", f"{PROJECT_DIR}/docker/omnidb"),
        ("docker/kafka-ui", f"{PROJECT_DIR}/docker/kafka-ui"),
        ("docker-compose.yml", f"{PROJECT_DIR}/docker-compose.yml"),
        ("docker-compose.offline.yml", f"{PROJECT_DIR}/docker-compose.offline.yml"),
        ("docker-compose.prod.yml", f"{PROJECT_DIR}/docker-compose.prod.yml"),
        ("backend/app/config.py", f"{PROJECT_DIR}/backend/app/config.py"),
        ("backend/app/redpanda_service.py", f"{PROJECT_DIR}/backend/app/redpanda_service.py"),
    ]
    for local_rel, remote in upload_paths:
        local_abs = os.path.join(ROOT, local_rel)
        if os.path.isdir(local_abs):
            upload_tree(sftp, local_abs, remote)
        else:
            print(f"Upload {local_abs} -> {remote}")
            sftp.put(local_abs, remote)
    sftp.close()

    script = f"""set -e
cd {PROJECT_DIR}
export COMPOSE_PROJECT_NAME=quicknav

echo '==> Check OmniDB vendor tarball (offline server cannot wget GitHub)'
if [ ! -f docker/omnidb/vendor/OmniDB-3.0.3b.tar.gz ]; then
  echo "MISSING_VENDOR: place OmniDB-3.0.3b.tar.gz under docker/omnidb/vendor/ on server"
  exit 3
fi

echo '==> Check required base images (offline, no pull)'
for img in python:3.12-slim-bookworm provectuslabs/kafka-ui:v0.7.2; do
  if ! docker image inspect "$img" >/dev/null 2>&1; then
    echo "MISSING_IMAGE: $img"
    echo "Load offline tar first, e.g.: docker load -i offline/docker-images/quicknav-images-arm64.tar"
    exit 2
  fi
  echo "OK $img"
done

echo '==> Remove old amd64 console containers'
docker rm -f quicknav-redpanda-console quicknav-redpanda 2>/dev/null || true

echo '==> Build ARM64 native consoles on server'
docker-compose -f docker-compose.yml -f docker-compose.offline.yml -f docker-compose.prod.yml build --pull=false omnidb-app kafka-ui backend

echo '==> Start services'
docker-compose -f docker-compose.yml -f docker-compose.offline.yml -f docker-compose.prod.yml up -d --no-build omnidb-app omnidb kafka-ui backend
sleep 25

docker ps --format 'table {{.Names}}\\t{{.Status}}' | grep -E 'omnidb|kafka|backend' || true
echo '--- omnidb-app ---'
docker logs quicknav-omnidb-app --tail 12 2>&1 || true
echo '--- kafka-ui ---'
docker logs quicknav-kafka-ui --tail 12 2>&1 || true

docker exec quicknav-backend python - <<'PY'
import httpx
for name, url in [
    ('omnidb-app', 'http://omnidb-app:8000/omnidb_login/?user=admin&pwd=admin@123'),
    ('omnidb-proxy', 'http://omnidb:8081/'),
    ('kafka-ui', 'http://kafka-ui:8080/'),
]:
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True)
        print(name, r.status_code)
    except Exception as exc:
        print(name, 'FAIL', exc)
PY
echo DEPLOY_OK
"""
    stdin, stdout, stderr = ssh.exec_command("bash -s", timeout=1800)
    stdin.write(script)
    stdin.channel.shutdown_write()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    print(out)
    if err.strip():
        print(err)
    code = stdout.channel.recv_exit_status()
    ssh.close()
    if code != 0 or "DEPLOY_OK" not in out:
        if "MISSING_IMAGE" in out:
            print("\nServer missing base images. Export on a machine with Docker registry access:")
            print("  powershell -ExecutionPolicy Bypass -File scripts/docker/export-arm64.ps1")
            print("Then upload and load quicknav-images-arm64.tar on the server.")
        if "MISSING_VENDOR" in out:
            print("\nPlace OmniDB-3.0.3b.tar.gz on server at:")
            print(f"  {PROJECT_DIR}/docker/omnidb/vendor/OmniDB-3.0.3b.tar.gz")
            print("Download once (any machine with GitHub access):")
            print("  powershell -ExecutionPolicy Bypass -File scripts/docker/prepare-omnidb-vendor.ps1")
        return 1
    print("ARM64 native consoles built and started on server.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
