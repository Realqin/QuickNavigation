#!/usr/bin/env python3
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"
LOCAL_MAIN = r"E:\workspace\QuickNavigation\backend\app\main.py"
REMOTE_MAIN = "/opt/hlx/QuickNavigation/backend/app/main.py"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)

sftp = ssh.open_sftp()
print("Upload main.py fix...")
sftp.put(LOCAL_MAIN, REMOTE_MAIN)
sftp.close()

for cmd in [
    "docker restart quicknav-backend",
    "sleep 15",
    "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -E 'backend|frontend|mysql'",
    "docker logs quicknav-backend --tail 15 2>&1",
    "wget -q -S -O /dev/null http://127.0.0.1:8000/docs 2>&1 | head -3",
]:
    print("\n>>>", cmd)
    i, o, e = ssh.exec_command(cmd, timeout=120)
    print(o.read().decode())
    err = e.read().decode()
    if err.strip():
        print(err)

ssh.close()
