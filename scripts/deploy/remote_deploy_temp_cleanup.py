#!/usr/bin/env python3
"""Deploy backend temp-connection cleanup + frontend Redis menu page."""
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

BACKEND_FILES = [
    "backend/app/console_temp.py",
    "backend/app/embed_session_service.py",
    "backend/app/omnidb_service.py",
    "backend/app/redisinsight_service.py",
    "backend/app/routers/api.py",
]


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
    for rel in BACKEND_FILES:
        local = os.path.join(ROOT, rel)
        remote = f"{PROJECT_DIR}/{rel.replace(chr(92), '/')}"
        print(f"Upload {local} -> {remote}")
        sftp.put(local, remote)
    sftp.close()

    script = f"""set -e
cd {PROJECT_DIR}
export COMPOSE_PROJECT_NAME=quicknav
docker-compose -f docker-compose.yml -f docker-compose.offline.yml -f docker-compose.prod.yml restart backend
sleep 4
docker exec quicknav-backend python -c "from app.embed_session_service import purge_temporary_connections_for_connection_method_menu, CONSOLE_DATABASE, CONSOLE_REDIS; from app.database import SessionLocal; db=SessionLocal(); purge_temporary_connections_for_connection_method_menu(db, CONSOLE_DATABASE); purge_temporary_connections_for_connection_method_menu(db, CONSOLE_REDIS); db.close(); print('PURGE_OK')"
"""
    i, o, e = ssh.exec_command("bash -s", timeout=120)
    i.write(script)
    i.channel.shutdown_write()
    out = o.read().decode(errors="replace")
    err = e.read().decode(errors="replace")
    print(out)
    if err.strip():
        print(err)
    ssh.close()
    return 0 if "PURGE_OK" in out else 1

if __name__ == "__main__":
    raise SystemExit(main())
