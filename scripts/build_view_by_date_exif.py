#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import subprocess

from lib.env import require_env, optional_env
from lib.fs_filters import is_shafferography_sidecar, should_skip_filename

PHOTO_ARCHIVE = require_env("PHOTO_ARCHIVE")
CANON = require_env("CANON")
RUN_LABEL = optional_env("RUN_LABEL", "").strip()

if RUN_LABEL:
    VIEW_ROOT = os.path.join(PHOTO_ARCHIVE, "VIEWS", "by-date", RUN_LABEL)
else:
    VIEW_ROOT = os.path.join(PHOTO_ARCHIVE, "VIEWS", "by-date")

os.makedirs(VIEW_ROOT, exist_ok=True)

rx = re.compile(r"^(\d{4}):(\d{2}):(\d{2})\b")

created = 0
no_exif = 0
skipped = 0

for fn in os.listdir(CANON):
    if should_skip_filename(fn) or is_shafferography_sidecar(fn):
        skipped += 1
        continue

    src = os.path.join(CANON, fn)
    if not os.path.isfile(src):
        continue

    cmd = ["exiftool", "-DateTimeOriginal", "-CreateDate", "-s", "-s", "-s", src]
    p = subprocess.run(cmd, capture_output=True, text=True)
    lines = [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]

    ymd = None
    for ln in lines:
        m = rx.match(ln)
        if m:
            ymd = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            break

    if ymd:
        yyyy, mm, _ = ymd.split("-")
        dest_dir = os.path.join(VIEW_ROOT, yyyy, mm, ymd)
    else:
        dest_dir = os.path.join(VIEW_ROOT, "NO_EXIF")
        no_exif += 1

    os.makedirs(dest_dir, exist_ok=True)

    sha, ext = os.path.splitext(fn)
    base = f"{ymd}_{sha[:10]}{ext}" if ymd else f"NOEXIF_{sha[:10]}{ext}"
    dest = os.path.join(dest_dir, base)

    if not os.path.exists(dest):
        os.symlink(os.path.relpath(src, dest_dir), dest)
        created += 1

print(f"Created {created:,} symlinks")
print(f"Placed {no_exif:,} files under NO_EXIF/ (fallback used)")
print(f"Skipped {skipped:,} non-media artifacts")
print("Done.")
