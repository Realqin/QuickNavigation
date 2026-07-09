#!/usr/bin/env python3
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)

cmds = [
    "docker logs quicknav-frontend 2>&1 | grep -E '502|503|504|error|upstream' | tail -20",
    "docker logs quicknav-backend 2>&1 | grep -c 'Application startup failed'",
    "docker logs quicknav-backend 2>&1 | grep 'Application startup complete' | tail -3",
]

for cmd in cmds:
    print("\n>>>", cmd)
    i, o, e = ssh.exec_command(cmd, timeout=60)
    print(o.read().decode(errors="replace").rstrip())

ssh.close()
