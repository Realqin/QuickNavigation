#!/usr/bin/env python3
"""Offline deploy qemu-x86_64-static to ARM server for amd64 Docker images."""
from __future__ import annotations

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


def extract_qemu_from_deb(deb_bytes: bytes) -> bytes:
    import io
    import lzma
    import tarfile

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


def download_qemu_binary() -> bytes:
    print(f"Downloading {QEMU_DEB_URL} ...")
    with urllib.request.urlopen(QEMU_DEB_URL, timeout=300) as resp:
        deb_bytes = resp.read()
    qemu = extract_qemu_from_deb(deb_bytes)
    if len(qemu) < 1024 * 1024:
        raise RuntimeError("extracted qemu binary too small")
    return qemu


def main() -> int:
    qemu_bin = download_qemu_binary()
    print(f"Downloaded qemu-x86_64-static ({len(qemu_bin) / 1024 / 1024:.1f} MB)")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)

    sftp = ssh.open_sftp()
    remote_tmp = "/tmp/qemu-x86_64-static"
    print(f"Uploading qemu to {QEMU_REMOTE} ...")
    with sftp.file(remote_tmp, "wb") as rf:
        rf.write(qemu_bin)
    sftp.close()

    script = f"""set -e
install -m 755 {remote_tmp} {QEMU_REMOTE}
mountpoint -q /proc/sys/fs/binfmt_misc || mount binfmt_misc -t binfmt_misc /proc/sys/fs/binfmt_misc
if ! ls /proc/sys/fs/binfmt_misc/qemu-x86_64 >/dev/null 2>&1; then
  echo ':qemu-x86_64:M::\\x7fELF\\x02\\x01\\x01\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x02\\x00\\x3e\\x00:\\xff\\xff\\xff\\xff\\xff\\xfe\\xfe\\xfe\\xff:\\xff\\xff\\xff\\xff\\xff\\xff\\xff\\xff:\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00:{QEMU_REMOTE}:OCF' > /proc/sys/fs/binfmt_misc/register
fi
ls /proc/sys/fs/binfmt_misc/qemu-x86_64

cd {PROJECT_DIR}
sed -i 's|PUBLIC_WEBHOOK_BASE_URL: http://192.168.6.127:8080|PUBLIC_WEBHOOK_BASE_URL: {PUBLIC_BASE}|g' docker-compose.yml

export COMPOSE_PROJECT_NAME=quicknav
docker-compose -f docker-compose.yml -f docker-compose.offline.yml up -d --no-build omnidb-app omnidb redpanda-console backend
sleep 30

docker ps --format 'table {{.Names}}\\t{{.Status}}' | grep -E 'omnidb|redpanda|backend'

echo '--- omnidb-app ---'
docker logs quicknav-omnidb-app --tail 8 2>&1 || true
echo '--- redpanda ---'
docker logs quicknav-redpanda-console --tail 8 2>&1 || true

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
    print("QEMU + embedded services fix completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
