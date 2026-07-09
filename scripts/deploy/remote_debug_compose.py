#!/usr/bin/env python3
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"
PROJECT = "/opt/hlx/QuickNavigation"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)

cmds = [
    "uname -m",
    "file /usr/local/bin/docker-compose",
    "/usr/local/bin/docker-compose version 2>&1; echo exit=$?",
    "ldd /usr/local/bin/docker-compose 2>&1 | head -5",
    f"cd {PROJECT} && COMPOSE_PROJECT_NAME=quicknav /usr/local/bin/docker-compose -f docker-compose.yml -f docker-compose.offline.yml config --services 2>&1; echo exit=$?",
    f"cd {PROJECT} && COMPOSE_PROJECT_NAME=quicknav /usr/local/bin/docker-compose -f docker-compose.yml -f docker-compose.offline.yml up -d --no-build 2>&1; echo exit=$?",
    "docker ps -a",
]
for cmd in cmds:
    print("\n>>>", cmd)
    i, o, e = ssh.exec_command(cmd, timeout=300)
    out = o.read().decode()
    err = e.read().decode()
    print(out)
    if err:
        print("STDERR:", err)
    print("exit", o.channel.recv_exit_status())

ssh.close()
