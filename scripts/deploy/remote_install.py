#!/usr/bin/env python3
"""Phase 1: install Docker on remote and upload project sources."""
from __future__ import annotations

import os
import sys
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = os.environ.get("DEPLOY_PASSWORD", "firefly")
ROOT = "/opt/hlx"
PROJECT_DIR = f"{ROOT}/QuickNavigation"

LOCAL_DOCKER_TGZ = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "offline", "docker-static", "docker-27.5.1.tgz")
)
LOCAL_PROJECT_TGZ = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "offline", "quicknav-project.tar.gz")
)


def run(ssh: paramiko.SSHClient, cmd: str, timeout: int = 600) -> tuple[int, str, str]:
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print(err.rstrip())
    return code, out, err


def remote_exists(sftp: paramiko.SFTPClient, path: str) -> bool:
    try:
        sftp.stat(path)
        return True
    except OSError:
        return False


def upload(sftp: paramiko.SFTPClient, local: str, remote: str) -> None:
    print(f"Upload {os.path.basename(local)} ({os.path.getsize(local)/1024/1024:.1f} MB)")
    sftp.put(local, remote)


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)
    sftp = ssh.open_sftp()

    run(ssh, f"mkdir -p {ROOT}/docker-static {PROJECT_DIR}/offline/docker-images")

    remote_docker = f"{ROOT}/docker-static/docker-27.5.1.tgz"
    if not remote_exists(sftp, remote_docker):
        upload(sftp, LOCAL_DOCKER_TGZ, remote_docker)

    upload(sftp, LOCAL_PROJECT_TGZ, f"{ROOT}/quicknav-project.tar.gz")

    _, out, _ = run(ssh, "docker version 2>/dev/null | head -3 || echo NO_DOCKER")
    if "NO_DOCKER" in out or "version" not in out:
        code, _, _ = run(
            ssh,
            f"""
set -e
cd {ROOT}/docker-static && tar xzf docker-27.5.1.tgz
cp docker/* /usr/bin/
groupadd -f docker 2>/dev/null || true
cat > /etc/systemd/system/docker.service <<'EOF'
[Unit]
Description=Docker
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/dockerd
Restart=always

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable docker
systemctl start docker
sleep 4
docker version
""",
            timeout=120,
        )
        if code != 0:
            return code

    run(ssh, f"mkdir -p {PROJECT_DIR} && cd {PROJECT_DIR} && tar xzf {ROOT}/quicknav-project.tar.gz")
    run(ssh, f"cp -f {ROOT}/docker-images/quicknav-images.tar {PROJECT_DIR}/offline/docker-images/ 2>/dev/null || true")
    run(ssh, f"uname -m && docker version && ls -la {PROJECT_DIR} | head")

    sftp.close()
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
