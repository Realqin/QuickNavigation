#!/usr/bin/env python3
"""Upload ARM64 base images (python + kafka-ui) to server and load."""
import os
import subprocess
import tempfile

import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"
PROJECT_DIR = "/opt/hlx/QuickNavigation"
IMAGES = ["python:3.12-slim-bookworm", "provectuslabs/kafka-ui:v0.7.2"]


def run(cmd: list[str]) -> None:
    print(">>>", " ".join(cmd))
    subprocess.check_call(cmd)


def main() -> int:
    for img in IMAGES:
        run(["docker", "pull", "--platform", "linux/arm64", img])
        arch = subprocess.check_output(
            ["docker", "image", "inspect", img, "--format", "{{.Architecture}}"],
            text=True,
        ).strip()
        print(f"{img} -> {arch}")
        if arch != "arm64":
            raise SystemExit(f"Expected arm64 for {img}, got {arch}")

    with tempfile.TemporaryDirectory() as tmp:
        tar_path = os.path.join(tmp, "base-images-arm64.tar")
        run(["docker", "save", "-o", tar_path] + IMAGES)
        size_mb = os.path.getsize(tar_path) / 1024 / 1024
        print(f"Tar size: {size_mb:.1f} MB")

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)
        sftp = ssh.open_sftp()
        remote_tar = "/tmp/base-images-arm64.tar"
        print(f"Upload -> {remote_tar}")
        sftp.put(tar_path, remote_tar)
        sftp.close()

        stdin, stdout, stderr = ssh.exec_command(f"docker load -i {remote_tar} && rm -f {remote_tar}", timeout=600)
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        print(out)
        if err.strip():
            print(err)
        code = stdout.channel.recv_exit_status()
        ssh.close()
        if code != 0:
            return 1
    print("Base images loaded on server.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
