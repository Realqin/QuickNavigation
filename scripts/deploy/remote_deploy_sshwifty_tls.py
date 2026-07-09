#!/usr/bin/env python3
"""Deploy Sshwifty HTTPS proxy + backend/frontend URL fixes to remote server."""
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
    frontend_build = subprocess.run(
        ["npm", "run", "build"],
        cwd=os.path.join(ROOT, "frontend"),
        shell=True,
    )
    if frontend_build.returncode != 0:
        return frontend_build.returncode

    frontend_deploy = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "deploy", "remote_deploy_frontend.py")],
    )
    if frontend_deploy.returncode != 0:
        return frontend_deploy.returncode

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting {USER}@{HOST} ...")
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    sftp = ssh.open_sftp()

    upload_tree(sftp, os.path.join(ROOT, "docker", "sshwifty"), f"{PROJECT_DIR}/docker/sshwifty")
    for rel in (
        "docker-compose.prod.yml",
        "backend/app/sshwifty_service.py",
        "backend/app/config.py",
    ):
        local_abs = os.path.join(ROOT, rel)
        remote = f"{PROJECT_DIR}/{rel.replace(chr(92), '/')}"
        print(f"Upload {local_abs} -> {remote}")
        sftp.put(local_abs, remote)
    sftp.close()

    compose = (
        "export COMPOSE_PROJECT_NAME=quicknav && "
        "docker-compose -f docker-compose.yml "
        "-f docker-compose.offline.yml -f docker-compose.prod.yml"
    )
    script = f"""set -e
cd {PROJECT_DIR}
{compose} build sshwifty backend
{compose} up -d --force-recreate sshwifty backend
sleep 3
echo '=== sshwifty TLS probe ==='
docker exec quicknav-sshwifty wget -S -O /dev/null --no-check-certificate https://127.0.0.1:8182/ 2>&1 | head -15 || true
echo DEPLOY_OK
"""
    print("Rebuilding sshwifty/backend on server...")
    i, o, e = ssh.exec_command("bash -s", timeout=600)
    i.write(script)
    i.channel.shutdown_write()
    out = o.read().decode(errors="replace")
    err = e.read().decode(errors="replace")
    print(out)
    if err.strip():
        print(err)
    ssh.close()
    if "DEPLOY_OK" not in out:
        print("Deploy failed", file=sys.stderr)
        return 1
    print("Sshwifty HTTPS deploy complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
