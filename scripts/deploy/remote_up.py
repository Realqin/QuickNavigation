#!/usr/bin/env python3
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"
PROJECT = "/opt/hlx/QuickNavigation"


def run(ssh, cmd, timeout=600):
    print(f"\n>>> {cmd}")
    i, o, e = ssh.exec_command(cmd, timeout=timeout)
    out = o.read().decode(errors="replace")
    err = e.read().decode(errors="replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print(err.rstrip())
    return code, out, err


ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)

run(ssh, "ls -lh /usr/local/bin/docker-compose; file /usr/local/bin/docker-compose")
run(ssh, "docker-compose version 2>&1 | head -5")

code, out, err = run(
    ssh,
    f"cd {PROJECT} && COMPOSE_PROJECT_NAME=quicknav docker-compose -f docker-compose.yml -f docker-compose.offline.yml up -d --no-build 2>&1",
    timeout=600,
)
print(f"compose up exit: {code}")

run(ssh, "sleep 10")
run(ssh, "docker ps -a")
run(ssh, "docker logs quicknav-backend --tail 20 2>&1 || true")
run(ssh, "docker logs quicknav-mysql --tail 10 2>&1 || true")
run(ssh, "wget -q -S -O /dev/null http://127.0.0.1:8080 2>&1 | head -5 || true")

ssh.close()
