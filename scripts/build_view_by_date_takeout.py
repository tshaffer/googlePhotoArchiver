#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from lib.env import require_env, split_env
from lib.fs_filters import is_shafferography_sidecar, should_skip_filename

PHOTO_ARCHIVE = require_env("PHOTO_ARCHIVE")
CANON = require_env("CANON")
ACCOUNTS = split_env("ACCOUNTS_STR")  # REQUIRED (via env.py)

TAKEOUT_ROOT = os.path.join(PHOTO_ARCHIVE, "GOOGLE_TAKEOUT")
VIEW_ROOT = os.path.join(PHOTO_ARCHIVE, "VIEWS", "by-date-takeout")

MEDIA_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".heic", ".tif", ".tiff",
    ".mp4", ".mov", ".m4v", ".avi", ".3gp", ".mpg", ".mpeg", ".webm",
}

# Canonical filename pattern: <64-hex-sha256><ext>
RX_CANON = re.compile(r"^(?P<sha>[0-9a-f]{64})(?P<ext>\.[^./\\]+)$", re.IGNORECASE)


def sha256_file(path: str, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def is_media(path: str) -> bool:
    return Path(path).suffix.lower() in MEDIA_EXTS


def parse_google_ts_seconds(js: dict):
    def get_ts(key):
        val = js.get(key)
        if isinstance(val, dict):
            ts = val.get("timestamp")
            if ts is not None:
                try:
                    return int(ts)
                except Exception:
                    return None
        return None

    return get_ts("photoTakenTime") or get_ts("creationTime")


def norm(s: str) -> str:
    return s.strip().lower()


# Build canonical index: sha -> canonical filepath
canon_by_sha: dict[str, str] = {}
for fn in os.listdir(CANON):
    if should_skip_filename(fn) or is_shafferography_sidecar(fn):
        continue
    m = RX_CANON.match(fn)
    if not m:
        continue
    sha = m.group("sha").lower()
    p = os.path.join(CANON, fn)
    if os.path.isfile(p):
        canon_by_sha[sha] = p

canon_hashes = set(canon_by_sha.keys())

# Build index of supplemental metadata JSON: (dirpath, media_filename_lower) -> timestamp
index: dict[tuple[str, str], int] = {}
json_scanned = 0

for acct in ACCOUNTS:
    base = os.path.join(TAKEOUT_ROOT, acct, "unzipped")
    if not os.path.isdir(base):
        continue

    for dirpath, _, filenames in os.walk(base):
        for fn in filenames:
            if should_skip_filename(fn):
                continue
            if not fn.lower().endswith(".supplemental-metadata.json"):
                continue

            json_scanned += 1
            json_path = os.path.join(dirpath, fn)
            media_name = fn[: -len(".supplemental-metadata.json")]
            key = (dirpath, norm(media_name))

            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    js = json.load(f)
            except Exception:
                continue

            ts = parse_google_ts_seconds(js)
            if ts is None:
                continue

            prev = index.get(key)
            if prev is None or ts < prev:
                index[key] = ts

os.makedirs(VIEW_ROOT, exist_ok=True)

created = 0
matched_to_json = 0
no_json_match = 0

for acct in ACCOUNTS:
    base = os.path.join(TAKEOUT_ROOT, acct, "unzipped")
    if not os.path.isdir(base):
        continue

    for dirpath, _, filenames in os.walk(base):
        for fn in filenames:
            if should_skip_filename(fn):
                continue

            media_path = os.path.join(dirpath, fn)
            if not is_media(media_path):
                continue

            sha = sha256_file(media_path).lower()
            canon_src = canon_by_sha.get(sha)
            if not canon_src:
                continue

            key = (dirpath, norm(fn))
            ts = index.get(key)
            if ts is None:
                no_json_match += 1
                continue

            matched_to_json += 1
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            yyyy = dt.strftime("%Y")
            mm = dt.strftime("%m")
            ymd = dt.strftime("%Y-%m-%d")

            dest_dir = os.path.join(VIEW_ROOT, yyyy, mm, ymd)
            os.makedirs(dest_dir, exist_ok=True)

            ext = Path(canon_src).suffix.lower()
            dest_name = f"{ymd}_{sha[:10]}{ext}"
            dest = os.path.join(dest_dir, dest_name)

            if not os.path.exists(dest):
                os.symlink(os.path.relpath(canon_src, dest_dir), dest)
                created += 1

print(f"Canonical items indexed (by filename hash): {len(canon_hashes):,}")
print(f"Supplemental JSON scanned: {json_scanned:,}")
print(f"Matched canonical items to JSON dates: {matched_to_json:,}")
print(f"No supplemental JSON match (folder+filename): {no_json_match:,}")
print(f"Created symlinks: {created:,}")
print("Done.")
