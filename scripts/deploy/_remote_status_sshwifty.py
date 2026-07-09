#!/usr/bin/env python3
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"

script = r"""
echo '=== containers ==='
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
echo
echo '=== sshwifty TLS ==='
docker exec quicknav-sshwifty wget -S -O /dev/null --no-check-certificate https://127.0.0.1:8182/ 2>&1 | head -12 || true
echo
echo '=== backend sshwifty base ==='
docker exec quicknav-backend python -c "
from app.sshwifty_service import build_sshwifty_public_base
print(build_sshwifty_public_base('192.168.6.189'))
"
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)
i, o, e = ssh.exec_command("bash -s", timeout=60)
i.write(script)
i.channel.shutdown_write()
print(o.read().decode(errors="replace"))
err = e.read().decode(errors="replace")
if err.strip():
    print("STDERR:", err)
ssh.close()
