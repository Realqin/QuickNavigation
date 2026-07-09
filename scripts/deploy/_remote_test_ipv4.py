#!/usr/bin/env python3
import json
import paramiko

HOST = "192.168.6.189"
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username="root", password="firefly", timeout=30)

script = r"""
echo '=== ipv4 registry test ==='
getent ahostsv4 registry-1.docker.io | head -3
REG_IP=$(getent ahostsv4 registry-1.docker.io | awk 'NR==1{print $1}')
echo "registry ipv4=$REG_IP"
ping -c 2 -W 3 "$REG_IP" 2>&1 | tail -3
python3 - <<PY
import socket, urllib.request
ip = socket.gethostbyname('registry-1.docker.io')
print('gethostbyname', ip)
req = urllib.request.Request('https://registry-1.docker.io/v2/', headers={'Host':'registry-1.docker.io'})
# force connect to ipv4 by using custom opener... simpler test:
import subprocess
subprocess.run(['curl','-4','-sS','-o','/dev/null','-w','curl4 HTTP %{http_code}\n','--connect-timeout','15','https://registry-1.docker.io/v2/'], check=False)
PY
which curl || (apt-get update && apt-get install -y curl 2>&1 | tail -3)
curl -4 -sS -o /dev/null -w 'curl4 registry %{http_code}\n' --connect-timeout 15 https://registry-1.docker.io/v2/ 2>&1 || true
echo DONE
"""
i,o,e=ssh.exec_command("bash -s",timeout=120)
i.write(script); i.channel.shutdown_write()
print(o.read().decode(errors='replace'))
ssh.close()
