#!/usr/bin/env python3
"""Small helpers shared by the photo-archive pipeline scripts."""

from __future__ import annotations

import os


def require_env(name: str) -> str:
    v = os.environ.get(name)
    if v is None or str(v).strip() == "":
        raise SystemExit(f"ERROR: env var {name} is required")
    return v


def optional_env(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    if v is None or str(v).strip() == "":
        return default
    return v


def split_env(name: str, default: str = "") -> list[str]:
    raw = optional_env(name, default=default)
    return [x for x in raw.split() if x]
