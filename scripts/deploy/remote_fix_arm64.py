#!/usr/bin/env python3
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"
PROJECT = "/opt/hlx/QuickNavigation"
# Prefer arm64 tar uploaded by user
TAR = "/opt/hlx/quicknav-images-arm64.tar"


def run(ssh, cmd, timeout=900):
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

run(ssh, f"ls -lh {TAR}")
run(ssh, f"docker load -i {TAR}", timeout=1800)
run(ssh, "docker image inspect quicknav-backend:latest --format 'backend arch={{.Architecture}}'")
run(ssh, "docker image inspect mysql:8.0 --format 'mysql arch={{.Architecture}}'")

run(ssh, f"""
set -e
cd {PROJECT}
export COMPOSE_PROJECT_NAME=quicknav
docker-compose -f docker-compose.yml -f docker-compose.offline.yml down 2>/dev/null || true
docker-compose -f docker-compose.yml -f docker-compose.offline.yml up -d --no-build
sleep 12
docker-compose ps
""")

run(ssh, "docker ps --format '{{.Names}} {{.Status}} {{.Ports}}'")
run(ssh, "wget -q -O /dev/null --server-response http://127.0.0.1:8080 2>&1 | head -3 || true")
run(ssh, "wget -q -O /dev/null --server-response http://127.0.0.1:8000/docs 2>&1 | head -3 || true")
run(ssh, "docker logs quicknav-backend --tail 30 2>&1")
run(ssh, "docker logs quicknav-mysql --tail 10 2>&1")

ssh.close()
