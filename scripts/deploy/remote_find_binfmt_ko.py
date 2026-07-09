#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.6.189", username="root", password="firefly", timeout=20)

script = """
find /lib/modules -name 'binfmt_misc.ko*' 2>/dev/null | head -5
find / -name 'binfmt_misc.ko*' 2>/dev/null | head -5
rpm -qa 2>/dev/null | grep -i kernel | head -10
dpkg -l 2>/dev/null | grep -i 'linux-image\|linux-modules' | head -10
"""
i, o, e = ssh.exec_command("bash -s", timeout=60)
i.write(script)
i.channel.shutdown_write()
print(o.read().decode(errors="replace"))
ssh.close()
