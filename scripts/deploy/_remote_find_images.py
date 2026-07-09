#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.6.189", username="root", password="firefly", timeout=20)
cmds = [
    "find /opt/hlx -name '*.tar' -o -name '*arm64*' 2>/dev/null | head -20",
    "docker images -a --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}'",
    "for id in $(docker images -aq); do docker image inspect $id --format '{{.Id}} {{.Architecture}} {{.RepoTags}}' 2>/dev/null; done | grep -E 'python|kafka|omnidb|redpanda|bookworm' || true",
]
for c in cmds:
    stdin, stdout, stderr = ssh.exec_command(c, timeout=120)
    print("===", c[:80], "===")
    print(stdout.read().decode(errors="replace"))
ssh.close()
