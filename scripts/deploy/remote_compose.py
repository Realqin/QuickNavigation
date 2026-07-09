#!/usr/bin/env python3
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"

cmds = [
    "which wget curl python3 pip3 docker-compose 2>/dev/null; python3 --version 2>/dev/null",
    "docker image inspect mysql:8.0 --format 'mysql arch={{.Architecture}}' 2>/dev/null",
    "docker image inspect quicknav-backend:latest --format 'backend arch={{.Architecture}}' 2>/dev/null",
    "wget --timeout=15 -q -O /usr/local/bin/docker-compose https://github.com/docker/compose/releases/download/v2.32.4/docker-compose-linux-aarch64 2>&1; echo wget_exit=$?",
    "ls -lh /usr/local/bin/docker-compose 2>/dev/null; chmod +x /usr/local/bin/docker-compose 2>/dev/null; /usr/local/bin/docker-compose version 2>&1 | head -3",
]

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=20)
for cmd in cmds:
    print("\n>>>", cmd)
    stdin, stdout, stderr = c.exec_command(cmd, timeout=120)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    print(out)
    if err.strip():
        print("ERR:", err)
c.close()
