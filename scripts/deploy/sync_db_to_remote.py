#!/usr/bin/env python3
"""Export local QuickNavigation MySQL and import into remote server (full replace)."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = os.environ.get("DEPLOY_PASSWORD", "firefly")
REMOTE_ROOT = "/opt/hlx"
REMOTE_DUMP = f"{REMOTE_ROOT}/quicknavigation-sync.sql"
LOCAL_CONTAINER = "quicknav-mysql"
REMOTE_CONTAINER = "quicknav-mysql"
DB_NAME = "quicknavigation"
DB_USER = "quicknav"
DB_PASS = "quicknav123"
ROOT_PASS = "root123456"


def export_local_dump(path: str) -> None:
    print("Exporting local database...")
    proc = subprocess.run(
        [
            "docker",
            "exec",
            LOCAL_CONTAINER,
            "mysqldump",
            f"-u{DB_USER}",
            f"-p{DB_PASS}",
            "--single-transaction",
            "--routines",
            "--triggers",
            "--hex-blob",
            "--set-gtid-purged=OFF",
            DB_NAME,
        ],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stderr.decode(errors="replace"), file=sys.stderr)
        raise SystemExit(proc.returncode)
    with open(path, "wb") as f:
        f.write(proc.stdout)
    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"Local dump: {path} ({size_mb:.2f} MB)")


def run_remote(ssh: paramiko.SSHClient, script: str, timeout: int = 900) -> tuple[int, str]:
    print("Running remote import...")
    stdin, stdout, stderr = ssh.exec_command("bash -s", timeout=timeout)
    stdin.write(script)
    stdin.channel.shutdown_write()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print(err.rstrip())
    return code, out


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        dump_path = os.path.join(tmp, "quicknavigation-sync.sql")
        export_local_dump(dump_path)

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        print(f"Connecting {USER}@{HOST} ...")
        ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)

        run_remote(ssh, f"mkdir -p {REMOTE_ROOT}\n")
        sftp = ssh.open_sftp()
        print(f"Uploading dump -> {REMOTE_DUMP} ...")
        sftp.put(dump_path, REMOTE_DUMP)
        sftp.close()

        remote_script = f"""set -e
echo 'Stopping backend to avoid write conflicts...'
docker stop quicknav-backend 2>/dev/null || true

echo 'Recreating database {DB_NAME}...'
docker exec {REMOTE_CONTAINER} mysql -uroot -p{ROOT_PASS} -e "DROP DATABASE IF EXISTS {DB_NAME}; CREATE DATABASE {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; GRANT ALL PRIVILEGES ON {DB_NAME}.* TO '{DB_USER}'@'%'; FLUSH PRIVILEGES;"

echo 'Importing dump...'
docker exec -i {REMOTE_CONTAINER} mysql -uroot -p{ROOT_PASS} {DB_NAME} < {REMOTE_DUMP}

echo 'Restarting backend...'
docker start quicknav-backend
sleep 10
docker ps --format '{{.Names}} {{.Status}}' | grep -E 'mysql|backend|frontend' || true

echo 'Health check...'
if wget -q -O /dev/null http://127.0.0.1:8000/docs; then
  echo 'backend docs ok'
else
  echo 'backend docs check failed' >&2
  exit 1
fi
echo SYNC_OK
"""
        code, out = run_remote(ssh, remote_script)
        ssh.close()
        if code != 0 or "SYNC_OK" not in out:
            print("Database sync failed.", file=sys.stderr)
            return 1

        print("\nDatabase sync completed.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
