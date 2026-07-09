#!/usr/bin/env python3
"""Install Docker static binary and deploy QuickNavigation on remote Linux."""
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
LOCAL_IMAGE_TGZ = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "offline", "docker-images", "quicknav-images-arm64.tar")
)


def run(ssh: paramiko.SSHClient, cmd: str, timeout: int = 600) -> tuple[int, str, str]:
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    exit_code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print(err.rstrip())
    return exit_code, out, err


def remote_exists(sftp: paramiko.SFTPClient, path: str) -> bool:
    try:
        sftp.stat(path)
        return True
    except OSError:
        return False


def upload(sftp: paramiko.SFTPClient, local: str, remote: str) -> None:
    size_mb = os.path.getsize(local) / (1024 * 1024)
    print(f"Uploading {os.path.basename(local)} -> {remote} ({size_mb:.1f} MB)")
    sftp.put(local, remote)
    print("  done")


def main() -> int:
    if not os.path.isfile(LOCAL_DOCKER_TGZ):
        print(f"Missing {LOCAL_DOCKER_TGZ}", file=sys.stderr)
        return 1
    if not os.path.isfile(LOCAL_PROJECT_TGZ):
        print(f"Missing {LOCAL_PROJECT_TGZ}", file=sys.stderr)
        return 1
    if not os.path.isfile(LOCAL_IMAGE_TGZ):
        print(f"Missing arm64 image tar: {LOCAL_IMAGE_TGZ}", file=sys.stderr)
        print("Run: powershell -File scripts/docker/export-arm64.ps1", file=sys.stderr)
        return 1

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting {USER}@{HOST} ...")
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)
    sftp = ssh.open_sftp()

    run(ssh, f"mkdir -p {ROOT}/docker-static {PROJECT_DIR}/offline/docker-images")

    remote_docker_tgz = f"{ROOT}/docker-static/docker-27.5.1.tgz"
    if not remote_exists(sftp, remote_docker_tgz):
        upload(sftp, LOCAL_DOCKER_TGZ, remote_docker_tgz)
    else:
        print(f"Skip docker tgz (exists)")

    upload(sftp, LOCAL_PROJECT_TGZ, f"{ROOT}/quicknav-project.tar.gz")
    upload(sftp, LOCAL_IMAGE_TGZ, f"{PROJECT_DIR}/offline/docker-images/quicknav-images.tar")

    _, out, _ = run(ssh, "command -v docker || echo MISSING")
    if "MISSING" in out or not out.strip():
        install_cmds = f"""
set -e
cd {ROOT}/docker-static
tar xzf docker-27.5.1.tgz
cp docker/* /usr/bin/
groupadd -f docker 2>/dev/null || true
cat > /etc/systemd/system/docker.service <<'EOF'
[Unit]
Description=Docker Application Container Engine
After=network-online.target
Wants=network-online.target

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
"""
        code, _, _ = run(ssh, install_cmds, timeout=120)
        if code != 0:
            return code

    run(ssh, f"mkdir -p {PROJECT_DIR} && cd {PROJECT_DIR} && tar xzf {ROOT}/quicknav-project.tar.gz", timeout=180)

    deploy_cmds = f"""
set -e
cd {PROJECT_DIR}
export COMPOSE_PROJECT_NAME=quicknav
docker load -i offline/docker-images/quicknav-images.tar
docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d --no-build
sleep 5
docker compose ps
curl -s -o /dev/null -w 'HTTP %{{http_code}}\\n' http://127.0.0.1:8080 || true
"""
    code, _, _ = run(ssh, deploy_cmds, timeout=900)

    sftp.close()
    ssh.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
