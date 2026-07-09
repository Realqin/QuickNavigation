#!/usr/bin/env python3
import json
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)

script = r'''
TOKEN=$(wget -qO- --post-data='username=admin&password=admin123' \
  --header='Content-Type: application/x-www-form-urlencoded' \
  http://127.0.0.1:8080/api/auth/login | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "TOKEN_LEN=${#TOKEN}"

for path in \
  '/api/dict?type=project' \
  '/api/connections/home?project=1&environment=3' \
  '/api/logs?project=1&environment=3&limit=8'; do
  echo "=== $path ==="
  wget -qS -O /tmp/out.json --header="Authorization: Bearer $TOKEN" "http://127.0.0.1:8080$path" 2>&1 | head -6
  echo "body:" $(head -c 200 /tmp/out.json)
  echo
done

echo "=== backend errors (home/logs) ==="
docker logs quicknav-backend 2>&1 | grep -iE 'connections/home|/api/logs|error|traceback|exception' | tail -30
'''

i, o, e = ssh.exec_command("bash -s", timeout=90)
i.write(script)
i.channel.shutdown_write()
print(o.read().decode(errors="replace"))
err = e.read().decode(errors="replace")
if err.strip():
    print("ERR:", err)
ssh.close()
