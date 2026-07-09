#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.6.189", username="root", password="firefly", timeout=20)

script = """
modprobe binfmt_misc 2>&1; echo modprobe_exit=$?
lsmod | grep binfmt || true
ls /proc/sys/fs/binfmt_misc 2>&1 | head -5 || true
KVER=$(uname -r)
find /lib/modules/$KVER -name '*binfmt*' 2>/dev/null | head -10
"""
i, o, e = ssh.exec_command("bash -s", timeout=30)
i.write(script)
i.channel.shutdown_write()
print(o.read().decode())
print(e.read().decode())
ssh.close()
