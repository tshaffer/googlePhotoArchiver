#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import os
from collections import defaultdict
from pathlib import Path

from lib.env import require_env, optional_env, split_env

PHOTO_ARCHIVE = require_env("PHOTO_ARCHIVE")
ACCOUNTS = split_env("ACCOUNTS_STR")  # REQUIRED (via env.py)
PREFERRED_ACCOUNT = require_env("PREFERRED_ACCOUNT")
RUN_LABEL = optional_env("RUN_LABEL", "run")

TAKEOUT_ROOT = os.path.join(PHOTO_ARCHIVE, "GOOGLE_TAKEOUT")

# Put outputs under a per-run folder to avoid clobbering prior runs
OUT_DIR = os.path.join(PHOTO_ARCHIVE, "MANIFESTS", RUN_LABEL)
os.makedirs(OUT_DIR, exist_ok=True)

UNIQUE_CSV = os.path.join(OUT_DIR, "dedup_plan__unique.csv")
DUP_CSV = os.path.join(OUT_DIR, "dedup_plan__duplicates.csv")

MEDIA_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".heic", ".tif", ".tiff",
    ".mp4", ".mov", ".m4v", ".avi", ".3gp", ".mpg", ".mpeg", ".webm",
}


def is_media(p: str) -> bool:
    return Path(p).suffix.lower() in MEDIA_EXTS


def sha256_file(path: str, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def should_skip_filename(fn: str) -> bool:
    return fn.startswith("._") or fn == ".DS_Store"


if not ACCOUNTS:
    raise SystemExit("ERROR: ACCOUNTS_STR resolved to zero accounts")

if PREFERRED_ACCOUNT not in ACCOUNTS:
    raise SystemExit(
        "ERROR: PREFERRED_ACCOUNT must be one of ACCOUNTS_STR. "
        f"PREFERRED_ACCOUNT={PREFERRED_ACCOUNT!r} ACCOUNTS_STR={ACCOUNTS!r}"
    )

# sha256 -> list of occurrences
records_by_sha: dict[str, list[dict]] = defaultdict(list)
scanned_media_files = 0
missing_unzipped: list[str] = []

for acct in ACCOUNTS:
    base = os.path.join(TAKEOUT_ROOT, acct, "unzipped")
    if not os.path.isdir(base):
        missing_unzipped.append(base)
        continue

    for dirpath, _, filenames in os.walk(base):
        for fn in filenames:
            if should_skip_filename(fn):
                continue

            p = os.path.join(dirpath, fn)
            if not is_media(p):
                continue

            scanned_media_files += 1
            sha = sha256_file(p)
            rel = os.path.relpath(p, base)

            records_by_sha[sha].append(
                {
                    "account": acct,
                    "takeoutRoot": base,
                    "relativePath": rel,
                    "absPath": p,
                    "ext": Path(fn).suffix.lower(),
                }
            )

if missing_unzipped:
    msg = "ERROR: missing expected unzipped takeout directories:\n" + "\n".join(missing_unzipped)
    raise SystemExit(msg)

print(f"Run label: {RUN_LABEL}")
print(f"Accounts: {', '.join(ACCOUNTS)} (preferred={PREFERRED_ACCOUNT})")
print(f"Scanned media files: {scanned_media_files:,}")
print(f"Unique hashes found: {len(records_by_sha):,}")

unique_rows: list[dict] = []
dup_rows: list[dict] = []

for sha, recs in records_by_sha.items():
    # sort occurrences so preferred account wins
    recs_sorted = sorted(
        recs,
        key=lambda r: (
            0 if r["account"] == PREFERRED_ACCOUNT else 1,
            r["account"],
            r["relativePath"],
        ),
    )
    canonical = recs_sorted[0]

    unique_rows.append(
        {
            "sha256": sha,
            "ext": canonical["ext"],
            "account": canonical["account"],
            "relativePath": canonical["relativePath"],
            "absPath": canonical["absPath"],
            "runLabel": RUN_LABEL,
            "preferredAccount": PREFERRED_ACCOUNT,
            "occurrences": str(len(recs)),
        }
    )

    for r in recs_sorted[1:]:
        dup_rows.append(
            {
                "sha256": sha,
                "ext": r["ext"],
                "account": r["account"],
                "relativePath": r["relativePath"],
                "absPath": r["absPath"],
                "runLabel": RUN_LABEL,
                "preferredAccount": PREFERRED_ACCOUNT,
            }
        )

unique_rows.sort(key=lambda r: r["sha256"])
dup_rows.sort(key=lambda r: (r["sha256"], r["account"], r["relativePath"]))

unique_fields = [
    "sha256",
    "ext",
    "account",
    "relativePath",
    "absPath",
    "runLabel",
    "preferredAccount",
    "occurrences",
]
dup_fields = [
    "sha256",
    "ext",
    "account",
    "relativePath",
    "absPath",
    "runLabel",
    "preferredAccount",
]

with open(UNIQUE_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=unique_fields)
    w.writeheader()
    w.writerows(unique_rows)

with open(DUP_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=dup_fields)
    w.writeheader()
    w.writerows(dup_rows)

print(f"Wrote: {UNIQUE_CSV} ({len(unique_rows):,} rows)")
print(f"Wrote: {DUP_CSV} ({len(dup_rows):,} rows)")
