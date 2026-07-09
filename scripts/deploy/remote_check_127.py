#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.6.189", username="root", password="firefly", timeout=20)

script = """
for host port in "192.168.6.127 8080" "192.168.6.127 8081" "192.168.6.127 8082" "192.168.6.127 8000"; do
  set -- $host $port
  timeout 2 bash -c "echo >/dev/tcp/$1/$2" 2>/dev/null && echo "$1:$2 OPEN" || echo "$1:$2 CLOSED"
done
"""
i, o, e = ssh.exec_command("bash -s", timeout=30)
i.write(script)
i.channel.shutdown_write()
print(o.read().decode())
ssh.close()
