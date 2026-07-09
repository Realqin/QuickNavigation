#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.6.189", username="root", password="firefly", timeout=30)
script = """
docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -E 'omnidb|kafka|backend|redpanda'
echo '--- omnidb-app ---'
docker logs quicknav-omnidb-app --tail 20 2>&1
echo '--- kafka-ui ---'
docker logs quicknav-kafka-ui --tail 5 2>&1
docker exec quicknav-backend python - <<'PY'
import httpx
for name, url in [
    ('omnidb-app', 'http://omnidb-app:8000/'),
    ('omnidb-proxy', 'http://omnidb:8081/'),
    ('kafka-ui', 'http://kafka-ui:8080/'),
]:
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True)
        print(name, r.status_code)
    except Exception as exc:
        print(name, 'FAIL', exc)
PY
"""
i, o, e = ssh.exec_command("bash -s", timeout=120)
i.write(script)
i.channel.shutdown_write()
print(o.read().decode(errors="replace"))
if e.read().decode().strip():
    print("ERR:", e.read().decode())
ssh.close()
