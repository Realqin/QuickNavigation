#!/usr/bin/env python3
"""Finalize network: DNS + Docker registry mirror (docker.io blocked, daocloud OK)."""
import json
import paramiko

HOST = "192.168.6.189"
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username="root", password="firefly", timeout=30)

daemon = {
    "dns": ["223.5.5.5", "114.114.114.114"],
    "registry-mirrors": [
        "https://docker.m.daocloud.io",
        "https://docker.1ms.run",
    ],
    "ip6tables": False,
}
ssh.exec_command("mkdir -p /etc/docker")[1].read()
sftp = ssh.open_sftp()
with sftp.file("/etc/docker/daemon.json", "w") as f:
    f.write(json.dumps(daemon, indent=2) + "\n")
sftp.close()

script = r"""
set -e
ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf
systemctl restart docker
sleep 5
cd /opt/hlx/QuickNavigation
export COMPOSE_PROJECT_NAME=quicknav
docker-compose -f docker-compose.yml -f docker-compose.offline.yml -f docker-compose.prod.yml up -d --no-build

echo '=== connectivity summary ==='
echo -n 'DNS baidu: '; getent ahostsv4 www.baidu.com | awk 'NR==1{print $1}'
echo -n 'NTP sync: '; timedatectl | awk -F': ' '/System clock synchronized/{print $2}'
echo
echo '=== docker pull via mirror ==='
docker pull --platform linux/arm64 alpine:3.20 2>&1 | tail -6
docker info 2>/dev/null | grep -A3 'Registry Mirrors' || true
echo DONE
"""
i, o, e = ssh.exec_command("bash -s", timeout=300)
i.write(script)
i.channel.shutdown_write()
print(o.read().decode(errors="replace"))
err = e.read().decode(errors="replace")
if err.strip():
    print("ERR:", err)
ssh.close()
