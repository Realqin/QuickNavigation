#!/usr/bin/env python3
"""Enable Kafka UI context-path proxy on remote server + deploy frontend."""
from __future__ import annotations

import os
import subprocess
import sys

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "192.168.6.189")
USER = os.environ.get("DEPLOY_USER", "root")
PASSWORD = os.environ.get("DEPLOY_PASSWORD", "firefly")
PROJECT_DIR = os.environ.get("DEPLOY_PROJECT_DIR", "/opt/hlx/QuickNavigation")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def main() -> int:
    build = subprocess.run(["npm", "run", "build"], cwd=os.path.join(ROOT, "frontend"), shell=True)
    if build.returncode != 0:
        return build.returncode
    fe = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "deploy", "remote_deploy_frontend.py")])
    if fe.returncode != 0:
        return fe.returncode

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    sftp = ssh.open_sftp()
    local = os.path.join(ROOT, "docker-compose.yml")
    remote = f"{PROJECT_DIR}/docker-compose.yml"
    print(f"Upload {local} -> {remote}")
    sftp.put(local, remote)
    sftp.close()

    script = f"""set -e
cd {PROJECT_DIR}
export COMPOSE_PROJECT_NAME=quicknav
COMPOSE='docker-compose -f docker-compose.yml -f docker-compose.offline.yml -f docker-compose.prod.yml'
$COMPOSE up -d --force-recreate kafka-ui
sleep 8
python3 - <<'PY'
import urllib.request
url = 'http://127.0.0.1:8080/proxy/kafka/'
try:
    html = urllib.request.urlopen(url, timeout=15).read().decode('utf-8', 'replace')
    print('proxy status ok, len', len(html))
    print('has context path', '/proxy/kafka' in html[:4000])
except Exception as e:
    print('proxy failed', e)
PY
echo DEPLOY_OK
"""
    i, o, e = ssh.exec_command("bash -s", timeout=180)
    i.write(script)
    i.channel.shutdown_write()
    out = o.read().decode(errors="replace")
    err = e.read().decode(errors="replace")
    print(out)
    if err.strip():
        print(err)
    ssh.close()
    return 0 if "DEPLOY_OK" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
