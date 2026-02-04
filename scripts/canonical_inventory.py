#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
from datetime import datetime

from lib.env import require_env

PHOTO_ARCHIVE = require_env("PHOTO_ARCHIVE")
CANON = require_env("CANON")

OUT = os.path.join(PHOTO_ARCHIVE, "MANIFESTS", "canonical_inventory__by-hash.csv")

def should_skip(fn: str) -> bool:
    return fn.startswith("._") or fn == ".DS_Store" or fn.endswith(".json")

rows: list[dict] = []
generated = datetime.utcnow().isoformat(timespec="seconds") + "Z"

for fn in os.listdir(CANON):
    if should_skip(fn):
        continue
    p = os.path.join(CANON, fn)
    if not os.path.isfile(p):
        continue
    st = os.stat(p)
    sha, ext = os.path.splitext(fn)
    rows.append(
        {
            "generatedAtUtc": generated,
            "sha256": sha,
            "ext": ext.lower(),
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
        fieldnames=["generatedAtUtc","sha256","ext","bytes","mtimeEpochSec","fileName"],
    )
    w.writeheader()
    w.writerows(rows)

print(f"Wrote {len(rows):,} rows -> {OUT}")
