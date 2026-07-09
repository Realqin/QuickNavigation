#!/usr/bin/env python3
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)

cmds = [
    "docker ps --format '{{.Names}} {{.Status}}' | grep -E 'backend|frontend'",
    "docker logs quicknav-backend --tail 40 2>&1",
    "docker logs quicknav-frontend --tail 20 2>&1",
    "wget -q -S -O /dev/null 'http://127.0.0.1:8080/api/dict' 2>&1 | head -5",
    "wget -q -S -O /dev/null 'http://127.0.0.1:8080/api/connections/home?project=1&environment=1' 2>&1 | head -8",
    "wget -q -S -O /dev/null 'http://127.0.0.1:8080/api/logs?project=1&environment=1' 2>&1 | head -8",
    "wget -q -O - 'http://127.0.0.1:8000/api/connections/home?project=1&environment=1' 2>&1 | head -c 300",
]
for cmd in cmds:
    print("\n>>>", cmd)
    i, o, e = ssh.exec_command(cmd, timeout=60)
    out = o.read().decode(errors="replace")
    err = e.read().decode(errors="replace")
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print("ERR:", err.rstrip())

ssh.close()
