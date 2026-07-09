#!/usr/bin/env python3
import os
import paramiko

HOST = "192.168.6.189"
PROJECT = "/opt/hlx/QuickNavigation"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username="root", password="firefly", timeout=30)
sftp = ssh.open_sftp()
sftp.put(os.path.join(ROOT, "docker-compose.prod.yml"), f"{PROJECT}/docker-compose.prod.yml")
sftp.close()

script = f"""set -e
cd {PROJECT}
export COMPOSE_PROJECT_NAME=quicknav
docker-compose -f docker-compose.yml -f docker-compose.offline.yml -f docker-compose.prod.yml up -d --no-build
sleep 8
echo '=== container times (should be CST) ==='
for c in quicknav-backend quicknav-kafka-ui quicknav-omnidb-app quicknav-mysql; do
  echo -n "$c: "
  docker exec "$c" date '+%Y-%m-%d %H:%M:%S %Z (%z)' 2>/dev/null
done
echo DONE
"""
i, o, e = ssh.exec_command("bash -s", timeout=300)
i.write(script)
i.channel.shutdown_write()
print(o.read().decode(errors="replace"))
ssh.close()
