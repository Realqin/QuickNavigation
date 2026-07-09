#!/usr/bin/env python3
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)

script = r"""
echo '=== omnidb-app logs ==='
docker logs quicknav-omnidb-app --tail 30 2>&1

echo
echo '=== redpanda-console logs ==='
docker logs quicknav-redpanda-console --tail 30 2>&1

echo
echo '=== image architecture ==='
for img in quicknavigation-omnidb-app quicknavigation-redpanda-console omnidbteam/omnidb redpandadata/console; do
  docker image inspect "$img" --format '{{.Id}} {{.Architecture}} {{.Os}}' 2>/dev/null || echo "$img missing"
done

echo
echo '=== PUBLIC_WEBHOOK_BASE_URL ==='
docker exec quicknav-backend printenv PUBLIC_WEBHOOK_BASE_URL

echo
echo '=== network from backend ==='
docker exec quicknav-backend python - <<'PY'
import socket

def probe(host, port):
    s = socket.socket()
    s.settimeout(3)
    try:
        s.connect((host, port))
        print(f"{host}:{port} OK")
    except Exception as exc:
        print(f"{host}:{port} FAIL {exc}")
    finally:
        s.close()

for host, port in [
    ("10.100.0.239", 3306),
    ("10.100.0.211", 9092),
    ("10.109.0.21", 9092),
    ("10.100.0.239", 6379),
    ("10.100.0.239", 22),
    ("gitlab.bj.uniseas.com.cn", 80),
]:
    probe(host, port)
PY

echo
echo '=== try omnidb login API from backend ==='
docker exec quicknav-backend python - <<'PY'
import httpx
try:
    r = httpx.get('http://omnidb-app:8000/omnidb_login/', params={'user':'admin','pwd':'admin@123'}, timeout=5)
    print('omnidb-app status', r.status_code)
except Exception as e:
    print('omnidb-app FAIL', e)
try:
    r = httpx.get('http://omnidb:8081/', timeout=5)
    print('omnidb proxy status', r.status_code)
except Exception as e:
    print('omnidb proxy FAIL', e)
try:
    r = httpx.get('http://redpanda-console:8080/', timeout=5)
    print('redpanda status', r.status_code)
except Exception as e:
    print('redpanda FAIL', e)
PY
"""

i, o, e = ssh.exec_command("bash -s", timeout=120)
i.write(script)
i.channel.shutdown_write()
print(o.read().decode(errors="replace"))
err = e.read().decode(errors="replace")
if err.strip():
    print("ERR:", err)
ssh.close()
