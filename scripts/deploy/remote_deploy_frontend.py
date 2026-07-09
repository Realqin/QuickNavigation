#!/usr/bin/env python3
"""Upload frontend dist + nginx.conf to server and hot-reload quicknav-frontend."""
from __future__ import annotations

import os
import stat
import tarfile
import tempfile
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"
LOCAL_FRONTEND = r"E:\workspace\QuickNavigation\frontend"
REMOTE_TMP = "/tmp/quicknav-frontend-update.tar.gz"
CONTAINER = "quicknav-frontend"
KAFKA_PROVIDER = os.environ.get("KAFKA_CONSOLE_PROVIDER", "kafka-ui")


def resolve_nginx_conf() -> str:
    name = "nginx.kafka-ui.conf" if KAFKA_PROVIDER == "kafka-ui" else "nginx.redpanda.conf"
    return os.path.join(LOCAL_FRONTEND, name)


def add_dir(tar: tarfile.TarFile, src_dir: str, arc_prefix: str) -> None:
    for root, _, files in os.walk(src_dir):
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, src_dir).replace("\\", "/")
            tar.add(full, arcname=f"{arc_prefix}/{rel}")


def main() -> None:
    dist_dir = os.path.join(LOCAL_FRONTEND, "dist")
    nginx_conf = resolve_nginx_conf()
    if not os.path.isdir(dist_dir):
        raise SystemExit(f"missing dist: {dist_dir}")
    if not os.path.isfile(nginx_conf):
        raise SystemExit(f"missing nginx conf: {nginx_conf}")

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        with tarfile.open(tmp_path, "w:gz") as tar:
            add_dir(tar, dist_dir, "dist")
            tar.add(nginx_conf, arcname="nginx.conf")

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)

        sftp = ssh.open_sftp()
        print("Uploading frontend bundle...")
        sftp.put(tmp_path, REMOTE_TMP)
        sftp.close()

        script = f"""set -e
cd /tmp
rm -rf quicknav-frontend-update
mkdir -p quicknav-frontend-update
tar -xzf {REMOTE_TMP} -C quicknav-frontend-update
docker cp quicknav-frontend-update/dist/. {CONTAINER}:/usr/share/nginx/html/
docker cp quicknav-frontend-update/nginx.conf {CONTAINER}:/etc/nginx/conf.d/default.conf
docker exec {CONTAINER} nginx -t
docker exec {CONTAINER} nginx -s reload
echo DEPLOY_OK
"""
        print("Updating container...")
        i, o, e = ssh.exec_command("bash -s", timeout=180)
        i.write(script)
        i.channel.shutdown_write()
        out = o.read().decode(errors="replace")
        err = e.read().decode(errors="replace")
        print(out)
        if err.strip():
            print(err)
        if "DEPLOY_OK" not in out:
            raise SystemExit("frontend deploy failed")
        ssh.close()
        print("Frontend deployed successfully.")
    finally:
        os.remove(tmp_path)


if __name__ == "__main__":
    main()
