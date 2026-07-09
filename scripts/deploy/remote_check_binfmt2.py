#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.6.189", username="root", password="firefly", timeout=20)

script = """
grep -i binfmt /proc/config.gz 2>/dev/null | gunzip -c 2>/dev/null || zcat /proc/config.gz 2>/dev/null | grep -i binfmt || true
grep -i binfmt /boot/config-$(uname -r) 2>/dev/null || true
mkdir -p /proc/sys/fs/binfmt_misc
mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc 2>&1; echo mount_exit=$?
ls /proc/sys/fs/binfmt_misc 2>&1 | head -5
"""
i, o, e = ssh.exec_command("bash -s", timeout=30)
i.write(script)
i.channel.shutdown_write()
print(o.read().decode())
ssh.close()
