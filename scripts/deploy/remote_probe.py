#!/usr/bin/env python3
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=15)

cmds = [
    "command -v docker; command -v podman; command -v nerdctl",
    "ls /usr/bin/docker* /usr/local/bin/docker* 2>/dev/null || true",
    "dpkg -l | grep -i docker || true",
    "dpkg -l | grep -i containerd || true",
    "ls -la /opt/hlx/",
]
for cmd in cmds:
    stdin, stdout, stderr = c.exec_command(cmd)
    print(f"=== {cmd} ===")
    print(stdout.read().decode())
    err = stderr.read().decode().strip()
    if err:
        print("ERR:", err)
c.close()
