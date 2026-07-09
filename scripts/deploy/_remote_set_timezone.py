#!/usr/bin/env python3
"""Set online server clock to current Beijing time and TZ=Asia/Shanghai for Docker."""
from __future__ import annotations

import datetime
import zoneinfo

import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"
PROJECT = "/opt/hlx/QuickNavigation"
TZ = "Asia/Shanghai"

now_bj = datetime.datetime.now(zoneinfo.ZoneInfo(TZ))
time_str = now_bj.strftime("%Y-%m-%d %H:%M:%S")
print(f"Target Beijing time: {time_str}")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)

script = f"""set -e
echo '=== before ==='
date '+%Y-%m-%d %H:%M:%S %Z (%z)'
timedatectl status 2>/dev/null | head -8 || true

timedatectl set-timezone {TZ}
timedatectl set-time '{time_str}' 2>/dev/null || date -s '{time_str}'

# Prefer UTC for hardware clock; keeps DST/tz changes sane on embedded boards.
timedatectl set-local-rtc 0 2>/dev/null || true

echo '=== after host ==='
date '+%Y-%m-%d %H:%M:%S %Z (%z)'

echo '=== docker container times ==='
for c in quicknav-backend quicknav-kafka-ui quicknav-omnidb-app quicknav-mysql quicknav-frontend; do
  if docker ps --format '{{{{.Names}}}}' | grep -qx "$c"; then
    echo -n "$c: "
    docker exec "$c" date '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null || echo n/a
  fi
done
echo DONE
"""
stdin, stdout, stderr = ssh.exec_command("bash -s", timeout=120)
stdin.write(script)
stdin.channel.shutdown_write()
out = stdout.read().decode(errors="replace")
err = stderr.read().decode(errors="replace")
print(out)
if err.strip():
    print("ERR:", err)
code = stdout.channel.recv_exit_status()
ssh.close()
raise SystemExit(0 if "DONE" in out and code == 0 else code)
