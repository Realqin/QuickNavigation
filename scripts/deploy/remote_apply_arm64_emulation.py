#!/usr/bin/env python3
"""Upload ARM64 emulation compose overlay and restart OmniDB / Redpanda on remote."""
from __future__ import annotations

import io
import lzma
import os
import tarfile
import tempfile
import urllib.request

import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"
PROJECT_DIR = "/opt/hlx/QuickNavigation"
PUBLIC_BASE = "http://192.168.6.189:8080"
QEMU_REMOTE = "/usr/local/bin/qemu-x86_64-static"
QEMU_DEB_URL = (
    "https://mirrors.tuna.tsinghua.edu.cn/debian/pool/main/q/qemu/"
    "qemu-user-static_7.2+dfsg-7+deb12u18+b2_arm64.deb"
)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def extract_qemu_from_deb(deb_bytes: bytes) -> bytes:
    data = deb_bytes
    offset = 8
    while offset + 60 <= len(data):
        header = data[offset : offset + 60]
        name = header[:16].decode("ascii").strip()
        size = int(header[48:58].decode("ascii").strip())
        payload = data[offset + 60 : offset + 60 + size]
        if name.startswith("data.tar"):
            if name.endswith(".xz"):
                payload = lzma.decompress(payload)
            with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as tar:
                for member in tar.getmembers():
                    if member.name.endswith("qemu-x86_64-static"):
                        extracted = tar.extractfile(member)
                        if extracted is None:
                            raise RuntimeError("failed to extract qemu binary")
                        return extracted.read()
        offset = offset + 60 + size + (size % 2)
    raise RuntimeError("qemu-x86_64-static not found in deb package")


def ensure_qemu_binary() -> bytes:
    local_qemu = os.path.join(tempfile.gettempdir(), "qemu-x86_64-static")
    if os.path.isfile(local_qemu) and os.path.getsize(local_qemu) > 1024 * 1024:
        with open(local_qemu, "rb") as f:
            return f.read()
    print(f"Downloading {QEMU_DEB_URL} ...")
    with urllib.request.urlopen(QEMU_DEB_URL, timeout=300) as resp:
        deb_bytes = resp.read()
    qemu = extract_qemu_from_deb(deb_bytes)
    with open(local_qemu, "wb") as f:
        f.write(qemu)
    return qemu


def upload_tree(sftp: paramiko.SFTPClient, files: list[tuple[str, str]]) -> None:
    for local, remote in files:
        remote_dir = os.path.dirname(remote).replace("\\", "/")
        parts = remote_dir.split("/")
        path = ""
        for part in parts:
            if not part:
                continue
            path += f"/{part}"
            try:
                sftp.stat(path)
            except OSError:
                sftp.mkdir(path)
        print(f"Upload {local} -> {remote}")
        sftp.put(local, remote)


def main() -> int:
    qemu_bin = ensure_qemu_binary()
    print(f"QEMU binary size: {len(qemu_bin) / 1024 / 1024:.1f} MB")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)

    sftp = ssh.open_sftp()
    sftp.put(os.path.join(ROOT, "docker-compose.arm64-emulation.yml"), f"{PROJECT_DIR}/docker-compose.arm64-emulation.yml")
    sftp.put(os.path.join(ROOT, "docker-compose.prod.yml"), f"{PROJECT_DIR}/docker-compose.prod.yml")
    upload_tree(
        sftp,
        [
            (os.path.join(ROOT, "docker", "omnidb", "entrypoint-qemu.sh"), f"{PROJECT_DIR}/docker/omnidb/entrypoint-qemu.sh"),
            (os.path.join(ROOT, "docker", "redpanda", "entrypoint-qemu.sh"), f"{PROJECT_DIR}/docker/redpanda/entrypoint-qemu.sh"),
        ],
    )
    with sftp.file("/tmp/qemu-x86_64-static", "wb") as rf:
        rf.write(qemu_bin)
    sftp.close()

    script = f"""set -e
install -m 755 /tmp/qemu-x86_64-static {QEMU_REMOTE}
chmod +x {PROJECT_DIR}/docker/omnidb/entrypoint-qemu.sh {PROJECT_DIR}/docker/redpanda/entrypoint-qemu.sh
sed -i 's|docker-compose -f docker-compose.yml -f docker-compose.offline.yml|docker-compose -f docker-compose.yml -f docker-compose.offline.yml -f docker-compose.prod.yml -f docker-compose.arm64-emulation.yml|g' /opt/hlx/*.sh 2>/dev/null || true
cd {PROJECT_DIR}
sed -i 's|PUBLIC_WEBHOOK_BASE_URL: http://192.168.6.127:8080|PUBLIC_WEBHOOK_BASE_URL: {PUBLIC_BASE}|g' docker-compose.yml
grep PUBLIC_WEBHOOK docker-compose.yml

export COMPOSE_PROJECT_NAME=quicknav
docker-compose -f docker-compose.yml -f docker-compose.offline.yml -f docker-compose.prod.yml -f docker-compose.arm64-emulation.yml up -d --no-build omnidb-app omnidb redpanda-console backend
sleep 35

docker ps --format 'table {{.Names}}\\t{{.Status}}' | grep -E 'omnidb|redpanda|backend'

echo '--- omnidb-app ---'
docker logs quicknav-omnidb-app --tail 10 2>&1 || true
echo '--- redpanda ---'
docker logs quicknav-redpanda-console --tail 10 2>&1 || true

docker exec quicknav-backend python - <<'PY'
import httpx
for name, url in [
    ('omnidb-app', 'http://omnidb-app:8000/omnidb_login/?user=admin&pwd=admin@123'),
    ('omnidb-proxy', 'http://omnidb:8081/'),
    ('redpanda', 'http://redpanda-console:8080/'),
]:
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True)
        print(name, r.status_code)
    except Exception as exc:
        print(name, 'FAIL', exc)
PY
echo FIX_OK
"""
    stdin, stdout, stderr = ssh.exec_command("bash -s", timeout=600)
    stdin.write(script)
    stdin.channel.shutdown_write()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    print(out)
    if err.strip():
        print(err)
    code = stdout.channel.recv_exit_status()
    ssh.close()
    if code != 0 or "FIX_OK" not in out:
        return 1
    print("Embedded console fix completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
