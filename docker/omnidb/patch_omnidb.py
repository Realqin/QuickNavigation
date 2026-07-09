#!/usr/bin/env python3
from pathlib import Path

root = Path("/home/omnidb/OmniDB")
config = root / "config.py"
if not config.is_file():
    config = root / "OmniDB" / "config.py"
settings = root / "OmniDB" / "settings.py"
if not settings.is_file():
    settings = root / "OmniDB" / "OmniDB" / "settings.py"

if config.is_file():
    text = config.read_text(encoding="utf-8")
    text = text.replace("LISTENING_ADDRESS    = '127.0.0.1'", "LISTENING_ADDRESS    = '0.0.0.0'")
    config.write_text(text, encoding="utf-8")

if settings.is_file():
    lines = settings.read_text(encoding="utf-8").splitlines()
    settings.write_text(
        "\n".join(line for line in lines if "django_sass" not in line) + "\n",
        encoding="utf-8",
    )

server_py = root / "OmniDB" / "omnidb-server.py"
if server_py.is_file():
    lines = server_py.read_text(encoding="utf-8").splitlines()
    server_py.write_text(
        "\n".join(line for line in lines if "django_sass" not in line) + "\n",
        encoding="utf-8",
    )
