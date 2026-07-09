#!/usr/bin/env python3
import json
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)

cmds = [
    "grep -n 'LABEL_OTHER\\|seed_connections\\|普通连接' /opt/hlx/QuickNavigation/backend/app/main.py | head -20",
    "docker inspect quicknav-backend --format '{{.State.Status}} restarts={{.RestartCount}} started={{.State.StartedAt}}'",
    """python3 - <<'PY'
import json, urllib.request
req = urllib.request.Request(
    'http://127.0.0.1:8080/api/auth/login',
    data=json.dumps({'username':'admin','password':'admin123'}).encode(),
    headers={'Content-Type':'application/json'},
    method='POST',
)
with urllib.request.urlopen(req, timeout=15) as r:
    body = json.loads(r.read().decode())
token = body['access_token']
for path in [
    '/api/dict?type=project',
    '/api/connections/home?project=1&environment=3',
    '/api/logs?project=1&environment=3&limit=8',
]:
    req2 = urllib.request.Request(
        f'http://127.0.0.1:8080{path}',
        headers={'Authorization': f'Bearer {token}'},
    )
    with urllib.request.urlopen(req2, timeout=15) as r2:
        data = r2.read()
        print(path, r2.status, len(data), data[:120])
PY""",
    "docker logs quicknav-backend 2>&1 | tail -15",
]

for cmd in cmds:
    print("\n>>>", cmd[:120].replace("\n", " "))
    i, o, e = ssh.exec_command(cmd, timeout=90)
    out = o.read().decode(errors="replace")
    err = e.read().decode(errors="replace")
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print("ERR:", err.rstrip())

ssh.close()
