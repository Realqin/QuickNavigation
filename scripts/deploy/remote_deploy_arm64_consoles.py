#!/usr/bin/env python3
"""Backward-compatible entry: build ARM64 consoles on online server only."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from remote_build_consoles_on_server import main

if __name__ == "__main__":
    raise SystemExit(main())
