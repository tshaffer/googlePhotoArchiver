"""Shared filename filters for pipeline scans."""

from __future__ import annotations


def should_skip_filename(name: str) -> bool:
    return (
        not name
        or name.startswith("._")
        or name == ".DS_Store"
    )


def is_shafferography_sidecar(name: str) -> bool:
    return bool(name) and name.endswith(".shafferography.json")
