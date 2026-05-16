"""Utility for reading environment configuration."""
import sys
import os
import json
from pathlib import Path


def load_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
