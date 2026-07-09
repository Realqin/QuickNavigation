#!/usr/bin/env python3
"""Build ARM64 console images locally, upload to server, start (server has no PyPI/Docker Hub)."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "192.168.6.189")
USER = os.environ.get("DEPLOY_USER", "root")
PASSWORD = os.environ.get("DEPLOY_PASSWORD", "firefly")
PROJECT_DIR = os.environ.get("DEPLOY_PROJECT_DIR", "/opt/hlx/QuickNavigation")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def run(cmd: list[str], *, cwd: str | None = None, env: dict | None = None) -> None:
    print("\n>>>", " ".join(cmd))
    merged = os.environ.copy()
    if env:
        merged.update(env)
    subprocess.check_call(cmd, cwd=cwd or ROOT, env=merged)


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
            if name == ".gitkeep":
                continue
            local_path = os.path.join(base, name)
            remote_path = f"{remote_base}/{name}"
            print(f"Upload {local_path} -> {remote_path}")
            sftp.put(local_path, remote_path)


def main() -> int:
    vendor_tar = os.path.join(ROOT, "docker", "omnidb", "vendor", "OmniDB-3.0.3b.tar.gz")
    if not os.path.isfile(vendor_tar) or os.path.getsize(vendor_tar) < 100_000:
        print("Run scripts/docker/prepare-omnidb-vendor.ps1 first", file=sys.stderr)
        return 1

    build_env = {
        "COMPOSE_PROJECT_NAME": "quicknav",
        "DOCKER_DEFAULT_PLATFORM": "linux/arm64",
        "DOCKER_BUILDKIT": "1",
    }
    run(["docker", "compose", "build", "--pull=false", "omnidb-app", "kafka-ui", "backend"], env=build_env)

    images = ["quicknav-omnidb-app", "quicknav-kafka-ui", "quicknav-backend"]
    for img in images:
        arch = subprocess.check_output(
            ["docker", "image", "inspect", img, "--format", "{{.Architecture}}"],
            text=True,
        ).strip()
        print(f"{img}: {arch}")
        if arch != "arm64":
            raise SystemExit(f"{img} is {arch}, expected arm64")

    with tempfile.TemporaryDirectory() as tmp:
        tar_path = os.path.join(tmp, "console-images-arm64.tar")
        run(["docker", "save", "-o", tar_path] + images)
        print(f"Image tar: {os.path.getsize(tar_path) / 1024 / 1024:.1f} MB")

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

        remote_tar = "/tmp/console-images-arm64.tar"
        print(f"Upload image tar -> {remote_tar}")
        sftp.put(tar_path, remote_tar)
        sftp.close()

        script = f"""set -e
cd {PROJECT_DIR}
export COMPOSE_PROJECT_NAME=quicknav
docker load -i {remote_tar}
rm -f {remote_tar}
docker rm -f quicknav-redpanda-console quicknav-redpanda 2>/dev/null || true
docker-compose -f docker-compose.yml -f docker-compose.offline.yml -f docker-compose.prod.yml up -d --no-build omnidb-app omnidb kafka-ui backend
sleep 25
docker ps --format 'table {{.Names}}\\t{{.Status}}' | grep -E 'omnidb|kafka|backend' || true
echo '--- omnidb-app ---'
docker logs quicknav-omnidb-app --tail 15 2>&1 || true
echo '--- kafka-ui ---'
docker logs quicknav-kafka-ui --tail 15 2>&1 || true
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
        stdin, stdout, stderr = ssh.exec_command("bash -s", timeout=900)
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
            return 1
    print("Deployed ARM64 native consoles to server.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
