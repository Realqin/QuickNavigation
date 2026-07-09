#!/usr/bin/env python3
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)

cmds = [
    "uname -r",
    "lsmod | grep binfmt || true",
    "ls -la /proc/sys/fs/ 2>/dev/null | head -10",
    "docker run --rm --platform linux/amd64 alpine echo ok 2>&1 | tail -5",
    "test -x /usr/local/bin/qemu-x86_64-static && /usr/local/bin/qemu-x86_64-static --version 2>&1 | head -2",
]

for cmd in cmds:
    print("\n>>>", cmd)
    i, o, e = ssh.exec_command(cmd, timeout=120)
    print(o.read().decode(errors="replace").strip())
    err = e.read().decode(errors="replace").strip()
    if err:
        print("ERR:", err)
ssh.close()
