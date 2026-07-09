#!/usr/bin/env python3
"""Deploy QuickNavigation on remote Linux server."""
from __future__ import annotations

import os
import sys
import paramiko

HOST = os.environ.get("DEPLOY_HOST", "192.168.6.189")
USER = os.environ.get("DEPLOY_USER", "root")
PASSWORD = os.environ.get("DEPLOY_PASSWORD", "firefly")
ROOT = "/opt/hlx"
PROJECT = f"{ROOT}/QuickNavigation"
TAR_CANDIDATES = [
    f"{PROJECT}/offline/docker-images/quicknav-images-arm64.tar",
    f"{PROJECT}/offline/docker-images/quicknav-images.tar",
    f"{ROOT}/quicknav-images-arm64.tar",
    f"{ROOT}/docker-images/quicknav-images.tar",
    f"{ROOT}/quicknav-images-arm64.tar",
]


def run(ssh: paramiko.SSHClient, cmd: str, timeout: int = 900) -> tuple[int, str, str]:
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


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting {USER}@{HOST} ...")
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)

    run(ssh, f"ls -la {ROOT}")
    run(ssh, "docker version 2>/dev/null | head -8 || echo NO_DOCKER")
    run(ssh, "command -v docker-compose || command -v docker compose || echo NO_COMPOSE")

    _, out, _ = run(ssh, f"test -f {PROJECT}/docker-compose.yml && echo HAS_PROJECT || echo NO_PROJECT")
    if "NO_PROJECT" in out:
        run(ssh, f"find {ROOT} -maxdepth 3 -name docker-compose.yml 2>/dev/null")

    _, out, _ = run(ssh, "; ".join(f"test -f {p} && echo FOUND:{p}" for p in TAR_CANDIDATES))
    tar_file = None
    for line in out.splitlines():
        if line.startswith("FOUND:"):
            tar_file = line.split("FOUND:", 1)[1].strip()
            break
    if not tar_file:
        run(ssh, f"find {ROOT} -name '*.tar' 2>/dev/null | head -20")
        print("ERROR: no image tar found", file=sys.stderr)
        return 1
    print(f"Using tar: {tar_file}")

    # docker-compose v1 binary if missing
    _, out, _ = run(ssh, "command -v docker-compose || true")
    if not out.strip():
        local_compose = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "offline", "docker-static", "docker-compose-linux-aarch64")
        )
        if os.path.isfile(local_compose) and os.path.getsize(local_compose) > 1_000_000:
            sftp = ssh.open_sftp()
            print(f"Upload docker-compose from {local_compose}")
            sftp.put(local_compose, "/usr/local/bin/docker-compose")
            sftp.chmod("/usr/local/bin/docker-compose", 0o755)
            sftp.close()
        else:
            run(ssh, "wget -q -O /usr/local/bin/docker-compose https://github.com/docker/compose/releases/download/v2.32.4/docker-compose-linux-aarch64 && chmod +x /usr/local/bin/docker-compose")
        run(ssh, "docker-compose version | head -3")

    run(ssh, "systemctl start docker 2>/dev/null; sleep 2")

    code, _, _ = run(ssh, f"docker load -i {tar_file}", timeout=1800)
    if code != 0:
        return code

    deploy = f"""
set -e
cd {PROJECT}
export COMPOSE_PROJECT_NAME=quicknav
if command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  DC="docker compose"
fi
$DC -f docker-compose.yml -f docker-compose.offline.yml up -d --no-build
sleep 8
$DC ps
curl -s -o /dev/null -w 'frontend HTTP %{{http_code}}\\n' http://127.0.0.1:8080 || true
curl -s -o /dev/null -w 'backend HTTP %{{http_code}}\\n' http://127.0.0.1:8000/docs || true
docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}' | head -20
"""
    code, _, _ = run(ssh, deploy, timeout=600)
    ssh.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
