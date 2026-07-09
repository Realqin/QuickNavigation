#!/usr/bin/env python3
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)

cmds = [
    "uname -m",
    "docker info 2>/dev/null | grep -i architecture || true",
    "docker inspect quicknav-omnidb-app --format '{{.Image}}' 2>/dev/null",
    "docker image inspect $(docker inspect quicknav-omnidb-app --format '{{.Image}}' 2>/dev/null) --format '{{.Architecture}}' 2>/dev/null",
    "docker inspect quicknav-redpanda-console --format '{{.Image}}' 2>/dev/null",
    "docker image inspect $(docker inspect quicknav-redpanda-console --format '{{.Image}}' 2>/dev/null) --format '{{.Architecture}}' 2>/dev/null",
    """docker exec quicknav-backend python -c "import socket
for h,p in [('10.100.0.239',3306),('10.100.0.211',9092),('10.109.0.21',9092)]:
 s=socket.socket(); s.settimeout(3)
 try: s.connect((h,p)); print(h+':'+str(p),'OK')
 except Exception as e: print(h+':'+str(p),'FAIL',e)
 finally: s.close()" """,
    "grep -n PUBLIC_WEBHOOK /opt/hlx/QuickNavigation/docker-compose.yml",
    "ls /proc/sys/fs/binfmt_misc/ 2>/dev/null | head -5",
]

for cmd in cmds:
    print("\n>>>", cmd[:100])
    i, o, e = ssh.exec_command(cmd, timeout=60)
    out = o.read().decode(errors="replace").strip()
    err = e.read().decode(errors="replace").strip()
    if out:
        print(out)
    if err:
        print("ERR:", err)

ssh.close()
