#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.6.189", username="root", password="firefly", timeout=20)

script = """
echo '=== network ==='
curl -s -o /dev/null -w 'docker.io %{http_code}\\n' --connect-timeout 5 https://registry-1.docker.io/v2/ || echo docker.io fail
curl -s -o /dev/null -w 'daocloud %{http_code}\\n' --connect-timeout 5 https://docker.m.daocloud.io/v2/ || echo daocloud fail

echo '=== try pull python arm64 ==='
docker pull --platform linux/arm64 python:3.12-slim-bookworm 2>&1 | tail -5

echo '=== try pull kafka-ui arm64 ==='
docker pull --platform linux/arm64 provectuslabs/kafka-ui:v0.7.2 2>&1 | tail -5

echo '=== images ==='
docker images --format '{{.Repository}}:{{.Tag}} {{.ID}}' | grep -E 'python|kafka-ui|bookworm' || true
"""
stdin, stdout, stderr = ssh.exec_command("bash -s", timeout=600)
stdin.write(script)
stdin.channel.shutdown_write()
print(stdout.read().decode(errors="replace"))
e = stderr.read().decode(errors="replace")
if e.strip():
    print("ERR:", e)
print("exit", stdout.channel.recv_exit_status())
ssh.close()
