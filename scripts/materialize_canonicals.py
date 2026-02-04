#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
import shutil

from lib.env import require_env

PHOTO_ARCHIVE = require_env("PHOTO_ARCHIVE")
CANON = require_env("CANON")

UNIQUE_CSV = os.path.join(PHOTO_ARCHIVE, "MANIFESTS", "dedup_plan__unique.csv")
os.makedirs(CANON, exist_ok=True)

if not os.path.isfile(UNIQUE_CSV):
    raise SystemExit(f"ERROR: expected manifest not found: {UNIQUE_CSV}")

copied = 0
skipped = 0

with open(UNIQUE_CSV, newline="", encoding="utf-8") as f:
    r = csv.DictReader(f)
    for row in r:
        sha = (row.get("sha256") or "").strip()
        ext = (row.get("ext") or "").strip().lower()
        src = (row.get("absPath") or "").strip()
        if not sha or not ext or not src:
            continue

        dest = os.path.join(CANON, f"{sha}{ext}")

        if os.path.exists(dest):
            skipped += 1
            continue

        if not os.path.isfile(src):
            print(f"WARNING: missing source, skipping: {src}")
            continue

        shutil.copy2(src, dest)
        copied += 1

print(f"Copied new canonicals: {copied:,}")
print(f"Skipped (already present): {skipped:,}")
print("Done.")
