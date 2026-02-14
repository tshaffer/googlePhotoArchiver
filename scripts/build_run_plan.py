#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import os
import re
from collections import defaultdict
from pathlib import Path

from lib.env import require_env, optional_env, split_env
from lib.fs_filters import is_shafferography_sidecar, should_skip_filename
from lib.takeout_paths import takeout_unzipped_base

PHOTO_ARCHIVE = require_env("PHOTO_ARCHIVE")
CANON = require_env("CANON")
ACCOUNTS = split_env("ACCOUNTS_STR")  # REQUIRED (via env.py)
PREFERRED_ACCOUNT = require_env("PREFERRED_ACCOUNT")
RUN_LABEL = optional_env("RUN_LABEL", "run")

# Put outputs under a per-run folder to avoid clobbering prior runs
OUT_DIR = os.path.join(PHOTO_ARCHIVE, "MANIFESTS", RUN_LABEL)
os.makedirs(OUT_DIR, exist_ok=True)

UNIQUE_CSV = os.path.join(OUT_DIR, "dedup_plan__unique.csv")
DUP_CSV = os.path.join(OUT_DIR, "dedup_plan__duplicates.csv")
ALREADY_IN_CANON_CSV = os.path.join(OUT_DIR, "already_in_canon.csv")

MEDIA_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".heic", ".tif", ".tiff",
    ".mp4", ".mov", ".m4v", ".avi", ".3gp", ".mpg", ".mpeg", ".webm",
}

# Canonical filename pattern: <64-hex-sha256><ext>
RX_CANON = re.compile(r"^(?P<sha>[0-9a-f]{64})(?P<ext>\.[^./\\]+)$", re.IGNORECASE)


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


if not ACCOUNTS:
    raise SystemExit("ERROR: ACCOUNTS_STR resolved to zero accounts")

if PREFERRED_ACCOUNT not in ACCOUNTS:
    raise SystemExit(
        "ERROR: PREFERRED_ACCOUNT must be one of ACCOUNTS_STR. "
        f"PREFERRED_ACCOUNT={PREFERRED_ACCOUNT!r} ACCOUNTS_STR={ACCOUNTS!r}"
    )

# Load existing canonical hashes from CANON filenames
canon_hashes: set[str] = set()
if not os.path.isdir(CANON):
    raise SystemExit(f"ERROR: CANON directory does not exist: {CANON}")

for fn in os.listdir(CANON):
    if should_skip_filename(fn) or is_shafferography_sidecar(fn):
        continue
    m = RX_CANON.match(fn)
    if not m:
        continue
    canon_hashes.add(m.group("sha").lower())

# sha256 -> list of occurrences (ONLY those not already in CANON)
records_by_sha: dict[str, list[dict]] = defaultdict(list)

# sha256 -> list of occurrences already present in CANON
already_by_sha: dict[str, list[dict]] = defaultdict(list)

scanned_media_files = 0
skipped_already_in_canon = 0
missing_unzipped: list[str] = []

for acct in ACCOUNTS:
    base = str(takeout_unzipped_base(acct))
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
            sha = sha256_file(p).lower()
            rel = os.path.relpath(p, base)

            rec = {
                "account": acct,
                "takeoutRoot": base,
                "relativePath": rel,
                "absPath": p,
                "ext": Path(fn).suffix.lower(),
            }

            if sha in canon_hashes:
                already_by_sha[sha].append(rec)
                skipped_already_in_canon += 1
            else:
                records_by_sha[sha].append(rec)

if missing_unzipped:
    msg = "ERROR: missing expected unzipped takeout directories:\n" + "\n".join(missing_unzipped)
    raise SystemExit(msg)

print(f"Run label: {RUN_LABEL}")
print(f"Accounts: {', '.join(ACCOUNTS)} (preferred={PREFERRED_ACCOUNT})")
print(f"Existing canon hashes detected: {len(canon_hashes):,}")
print(f"Scanned takeout media files: {scanned_media_files:,}")
print(f"Takeout items already in CANON (skipped from plan): {skipped_already_in_canon:,}")
print(f"New-to-CANON unique hashes found: {len(records_by_sha):,}")

# Build manifests for NEW items only
unique_rows: list[dict] = []
dup_rows: list[dict] = []

for sha, recs in records_by_sha.items():
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

# Write “already in canon” report (for audit/debug)
already_rows: list[dict] = []
for sha, recs in already_by_sha.items():
    for r in sorted(recs, key=lambda x: (x["account"], x["relativePath"])):
        already_rows.append(
            {
                "sha256": sha,
                "ext": r["ext"],
                "account": r["account"],
                "relativePath": r["relativePath"],
                "absPath": r["absPath"],
                "runLabel": RUN_LABEL,
            }
        )

already_fields = ["sha256", "ext", "account", "relativePath", "absPath", "runLabel"]
already_rows.sort(key=lambda r: (r["sha256"], r["account"], r["relativePath"]))

with open(ALREADY_IN_CANON_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=already_fields)
    w.writeheader()
    w.writerows(already_rows)

print(f"Wrote: {UNIQUE_CSV} ({len(unique_rows):,} rows)")
print(f"Wrote: {DUP_CSV} ({len(dup_rows):,} rows)")
print(f"Wrote: {ALREADY_IN_CANON_CSV} ({len(already_rows):,} rows)")
