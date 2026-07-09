#!/usr/bin/env python3
"""Fix OmniDB / Kafka console on ARM server: enable amd64 emulation + prod env."""
from __future__ import annotations

import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"
PROJECT_DIR = "/opt/hlx/QuickNavigation"
PUBLIC_BASE = "http://192.168.6.189:8080"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)

script = f"""set -e
cd {PROJECT_DIR}

echo '==> Enable amd64 containers on aarch64 (qemu/binfmt)...'
if ! ls /proc/sys/fs/binfmt_misc/qemu-x86_64 >/dev/null 2>&1; then
  docker run --privileged --rm tonistiigi/binfmt --install amd64
fi
ls /proc/sys/fs/binfmt_misc/ | grep -E 'qemu|x86' || true

echo '==> Fix PUBLIC_WEBHOOK_BASE_URL for this server...'
sed -i 's|PUBLIC_WEBHOOK_BASE_URL: http://192.168.6.127:8080|PUBLIC_WEBHOOK_BASE_URL: {PUBLIC_BASE}|g' docker-compose.yml
grep PUBLIC_WEBHOOK_BASE_URL docker-compose.yml

echo '==> Recreate amd64-dependent services...'
export COMPOSE_PROJECT_NAME=quicknav
docker-compose -f docker-compose.yml -f docker-compose.offline.yml up -d --no-build omnidb-app omnidb redpanda-console backend

echo '==> Wait for services...'
sleep 20

echo '==> Container status ==>'
docker ps --format 'table {{.Names}}\\t{{.Status}}' | grep -E 'omnidb|redpanda|backend'

echo '==> omnidb-app log tail ==>'
docker logs quicknav-omnidb-app --tail 8 2>&1 || true

echo '==> redpanda log tail ==>'
docker logs quicknav-redpanda-console --tail 8 2>&1 || true

echo '==> API smoke from backend ==>'
docker exec quicknav-backend python - <<'PY'
import httpx
for name, url in [
    ('omnidb-app', 'http://omnidb-app:8000/omnidb_login/?user=admin&pwd=admin@123'),
    ('omnidb-proxy', 'http://omnidb:8081/'),
    ('redpanda', 'http://redpanda-console:8080/'),
]:
    try:
        r = httpx.get(url, timeout=10, follow_redirects=True)
        print(name, r.status_code)
    except Exception as exc:
        print(name, 'FAIL', exc)
PY

echo FIX_OK
"""

print("Applying ARM embedded-console fix on remote server...")
stdin, stdout, stderr = ssh.exec_command("bash -s", timeout=600)
stdin.write(script)
stdin.channel.shutdown_write()
out = stdout.read().decode(errors="replace")
err = stderr.read().decode(errors="replace")
print(out)
if err.strip():
    print(err)
code = stdout.channel.recv_exit_status()
ssh.close()

if code != 0 or "FIX_OK" not in out:
    raise SystemExit(f"Fix failed (exit={code})")
print("\nFix completed.")
