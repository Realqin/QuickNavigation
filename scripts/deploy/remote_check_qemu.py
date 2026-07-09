#!/usr/bin/env python3
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)

cmds = [
    "which qemu-x86_64-static qemu-x86_64 2>/dev/null; dpkg -l | grep -i qemu | head -10",
    "ls /usr/bin/qemu-* 2>/dev/null | head -10",
    "cat /proc/sys/fs/binfmt_misc/status 2>/dev/null || true",
    "apt-cache policy qemu-user-static 2>/dev/null | head -5",
    "yum list installed 2>/dev/null | grep -i qemu | head -5",
]

for cmd in cmds:
    print("\n>>>", cmd[:90])
    i, o, e = ssh.exec_command(cmd, timeout=30)
    print(o.read().decode(errors="replace").strip() or "(empty)")
    err = e.read().decode(errors="replace").strip()
    if err:
        print("ERR:", err)
ssh.close()
