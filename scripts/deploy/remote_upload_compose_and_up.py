#!/usr/bin/env python3
import os
import time
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"
PROJECT = "/opt/hlx/QuickNavigation"
LOCAL_COMPOSE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "offline", "docker-static", "docker-compose-linux-aarch64")
)


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
    return code


ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)

if not os.path.isfile(LOCAL_COMPOSE) or os.path.getsize(LOCAL_COMPOSE) < 1_000_000:
    print(f"Missing compose binary: {LOCAL_COMPOSE}", flush=True)
    raise SystemExit(1)

print(f"Upload docker-compose ({os.path.getsize(LOCAL_COMPOSE) / 1024 / 1024:.1f} MB)...")
sftp = ssh.open_sftp()
sftp.put(LOCAL_COMPOSE, "/usr/local/bin/docker-compose")
sftp.chmod("/usr/local/bin/docker-compose", 0o755)
sftp.close()

run(ssh, "ls -lh /usr/local/bin/docker-compose")
run(ssh, "docker-compose version")

run(
    ssh,
    f"cd {PROJECT} && COMPOSE_PROJECT_NAME=quicknav docker-compose -f docker-compose.yml -f docker-compose.offline.yml up -d --no-build",
    timeout=900,
)

print("\nWaiting for services...")
time.sleep(20)

run(ssh, "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")
run(ssh, "docker logs quicknav-backend --tail 30 2>&1 || true")
run(ssh, "docker logs quicknav-mysql --tail 10 2>&1 || true")
run(ssh, "wget -q -S -O /dev/null http://127.0.0.1:8080 2>&1 | head -5 || true")
run(ssh, "wget -q -S -O /dev/null http://127.0.0.1:8000/docs 2>&1 | head -5 || true")

ssh.close()
print("\nDeploy done. Open http://192.168.6.189:8080 (admin / admin123)")
