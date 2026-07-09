#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.6.189", username="root", password="firefly", timeout=20)
cmds = [
    "uname -m",
    "docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'",
    "docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.ID}}' | head -35",
    "test -f /opt/hlx/QuickNavigation/docker/omnidb/vendor/OmniDB-3.0.3b.tar.gz && ls -lh /opt/hlx/QuickNavigation/docker/omnidb/vendor/OmniDB-3.0.3b.tar.gz || echo NO_VENDOR",
    "grep -E 'kafka-ui|redpanda|127' /opt/hlx/QuickNavigation/docker-compose.yml 2>/dev/null | head -15",
]
for c in cmds:
    stdin, stdout, stderr = ssh.exec_command(c, timeout=60)
    print("===", c, "===")
    print(stdout.read().decode(errors="replace"))
    e = stderr.read().decode(errors="replace")
    if e.strip():
        print("ERR:", e)
ssh.close()
