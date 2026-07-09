#!/usr/bin/env python3
import json
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)

script = """python3 - <<'PY'
import json, urllib.request

req = urllib.request.Request(
    'http://127.0.0.1:8080/api/auth/login',
    data=json.dumps({'username':'admin','password':'admin123'}).encode(),
    headers={'Content-Type':'application/json'},
    method='POST',
)
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        body = json.loads(r.read().decode())
    token = body['access_token']
    for path in ['/api/dict?type=project', '/api/connections?project=1&environment=3']:
        req2 = urllib.request.Request(
            f'http://127.0.0.1:8080{path}',
            headers={'Authorization': f'Bearer {token}'},
        )
        with urllib.request.urlopen(req2, timeout=15) as r2:
            data = r2.read()
            print(path, r2.status, len(data))
except Exception as e:
    print('ERROR', e)
PY
docker exec quicknav-mysql mysql -uroot -proot123456 -N -e "SELECT COUNT(*) AS connections FROM quicknavigation.connections; SELECT COUNT(*) AS users FROM quicknavigation.users; SELECT COUNT(*) AS dict_items FROM quicknavigation.dict_items;" 2>/dev/null
docker ps --format '{{.Names}} {{.Status}}' | grep -E 'backend|mysql'
"""

i, o, e = ssh.exec_command("bash -s", timeout=60)
i.write(script)
i.channel.shutdown_write()
print(o.read().decode(errors="replace"))
err = e.read().decode(errors="replace")
if err.strip():
    print("ERR:", err)
ssh.close()
