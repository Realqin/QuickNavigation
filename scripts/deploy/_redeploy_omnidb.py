#!/usr/bin/env python3
import os
import subprocess
import tempfile
import paramiko

HOST = "192.168.6.189"
PROJECT = "/opt/hlx/QuickNavigation"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

with tempfile.TemporaryDirectory() as tmp:
    tar_path = os.path.join(tmp, "omnidb-app.tar")
    subprocess.check_call(["docker", "save", "-o", tar_path, "quicknav-omnidb-app"])
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username="root", password="firefly", timeout=30)
    sftp = ssh.open_sftp()
    sftp.put(os.path.join(ROOT, "docker/omnidb/entrypoint.sh"), f"{PROJECT}/docker/omnidb/entrypoint.sh")
    sftp.put(tar_path, "/tmp/omnidb-app.tar")
    sftp.close()
    script = f"""set -e
cd {PROJECT}
docker load -i /tmp/omnidb-app.tar
rm -f /tmp/omnidb-app.tar
export COMPOSE_PROJECT_NAME=quicknav
docker-compose -f docker-compose.yml -f docker-compose.offline.yml -f docker-compose.prod.yml up -d --no-build omnidb-app omnidb
sleep 15
docker ps --format 'table {{.Names}}\\t{{.Status}}' | grep omnidb
docker logs quicknav-omnidb-app --tail 15
docker exec quicknav-backend python - <<'PY'
import httpx
for u in ['http://omnidb-app:8000/', 'http://omnidb:8081/']:
    try:
        r = httpx.get(u, timeout=15, follow_redirects=True)
        print(u, r.status_code)
    except Exception as e:
        print(u, 'FAIL', e)
PY
"""
    i, o, e = ssh.exec_command("bash -s", timeout=300)
    i.write(script)
    i.channel.shutdown_write()
    print(o.read().decode(errors="replace"))
    ssh.close()
