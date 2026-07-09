#!/usr/bin/env python3
"""Test remote server's access to domestic Docker mirrors."""
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"

MIRRORS = [
    "https://docker.1ms.run/v2/",
    "https://docker.m.daocloud.io/v2/",
    "https://dockerproxy.com/v2/",
    "https://hub-mirror.c.163.com/v2/",
    "https://mirror.baidubce.com/v2/",
    "https://docker.nju.edu.cn/v2/",
]

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=20)

# wget is available, curl is not
for url in MIRRORS:
    cmd = f"wget --timeout=8 -q --spider {url} 2>&1; echo exit=$?"
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = c.exec_command(cmd, timeout=20)
    print(stdout.read().decode())

# Also check general internet
for url in ["https://www.baidu.com", "https://archive.kylinos.cn"]:
    cmd = f"wget --timeout=8 -q --spider {url} 2>&1; echo exit=$?"
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = c.exec_command(cmd, timeout=20)
    print(stdout.read().decode())

c.close()
