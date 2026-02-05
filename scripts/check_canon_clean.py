#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

from lib.env import require_env
from lib.fs_filters import should_skip_filename

CANON = require_env("CANON")

offenders: list[str] = []
for p in Path(CANON).rglob("*"):
    if not p.is_file():
        continue
    if should_skip_filename(p.name):
        offenders.append(str(p))
        if len(offenders) >= 10:
            break

if offenders:
    print(f"ERROR: found macOS junk files under CANON: {CANON}")
    for path in offenders:
        print(f" - {path}")
    if len(offenders) == 10:
        print(" - ...")
    raise SystemExit(1)

print(f"OK: CANON is clean (no AppleDouble/.DS_Store): {CANON}")
