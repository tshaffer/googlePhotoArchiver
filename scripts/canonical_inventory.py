#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
import re
from datetime import datetime

from lib.env import require_env, optional_env
from lib.fs_filters import is_shafferography_sidecar, should_skip_filename

PHOTO_ARCHIVE = require_env("PHOTO_ARCHIVE")
CANON = require_env("CANON")

RUN_LABEL = optional_env("RUN_LABEL", "").strip()

if RUN_LABEL:
    OUT = os.path.join(PHOTO_ARCHIVE, "MANIFESTS", RUN_LABEL, "canonical_inventory__by-hash.csv")
else:
    OUT = os.path.join(PHOTO_ARCHIVE, "MANIFESTS", "canonical_inventory__by-hash.csv")

RX_CANON = re.compile(r"^(?P<sha>[0-9a-f]{64})(?P<ext>\.[^./\\]+)$", re.IGNORECASE)


rows: list[dict] = []
generated = datetime.utcnow().isoformat(timespec="seconds") + "Z"
skipped_artifacts = 0
skipped_sidecars = 0
skipped_noncanonical_names = 0

for fn in os.listdir(CANON):
    if should_skip_filename(fn):
        skipped_artifacts += 1
        continue
    if is_shafferography_sidecar(fn):
        skipped_sidecars += 1
        continue

    m = RX_CANON.match(fn)
    if not m:
        skipped_noncanonical_names += 1
        continue

    p = os.path.join(CANON, fn)
    if not os.path.isfile(p):
        continue

    st = os.stat(p)
    rows.append(
        {
            "generatedAtUtc": generated,
            "sha256": m.group("sha").lower(),
            "ext": m.group("ext").lower(),
            "bytes": st.st_size,
            "mtimeEpochSec": int(st.st_mtime),
            "fileName": fn,
        }
    )

rows.sort(key=lambda r: r["sha256"])
os.makedirs(os.path.dirname(OUT), exist_ok=True)

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(
        f,
        fieldnames=["generatedAtUtc", "sha256", "ext", "bytes", "mtimeEpochSec", "fileName"],
    )
    w.writeheader()
    w.writerows(rows)

print(f"Wrote {len(rows):,} rows -> {OUT}")
print("Inventory mode: media-only (excluding .shafferography.json sidecars)")
print(f"Skipped {skipped_artifacts:,} macOS artifacts")
print(f"Skipped {skipped_sidecars:,} sidecars")
print(f"Skipped {skipped_noncanonical_names:,} non-canonical filenames (did not match sha256+ext)")
