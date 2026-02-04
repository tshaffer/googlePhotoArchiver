#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from lib.env import require_env, optional_env

PHOTO_ARCHIVE = require_env("PHOTO_ARCHIVE")
CANON = require_env("CANON")

RUN_LABEL = optional_env("RUN_LABEL", "run")
TAKEOUT_BATCH_ID = optional_env("TAKEOUT_BATCH_ID", RUN_LABEL)
INGEST_TOOL = optional_env("INGEST_TOOL", "dedupe-pipeline")

UNIQUE_CSV = os.path.join(PHOTO_ARCHIVE, "MANIFESTS", RUN_LABEL, "dedup_plan__unique.csv")
DUP_CSV = os.path.join(PHOTO_ARCHIVE, "MANIFESTS", RUN_LABEL, "dedup_plan__duplicates.csv")

if not os.path.isfile(UNIQUE_CSV):
    raise SystemExit(f"ERROR: expected manifest not found: {UNIQUE_CSV}")

PHOTO_URL_RX = re.compile(r"/photo/([^/?#]+)")


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def find_takeout_metadata_json(media_abs_path: str) -> Optional[str]:
    p = Path(media_abs_path)
    cand1 = str(p) + ".json"
    cand2 = str(p) + ".supplemental-metadata.json"
    if os.path.isfile(cand1):
        return cand1
    if os.path.isfile(cand2):
        return cand2
    cand3 = str(p.with_suffix("")) + ".supplemental-metadata.json"
    if os.path.isfile(cand3):
        return cand3
    return None


def deep_find_first_string_key(obj: Any, keys: set[str]) -> Optional[str]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and isinstance(v, str) and v.strip():
                return v.strip()
            found = deep_find_first_string_key(v, keys)
            if found:
                return found
    elif isinstance(obj, list):
        for it in obj:
            found = deep_find_first_string_key(it, keys)
            if found:
                return found
    return None


def extract_google_photo_ids(js: dict) -> list[str]:
    ids: set[str] = set()
    url = js.get("url")
    if isinstance(url, str):
        m = PHOTO_URL_RX.search(url)
        if m:
            ids.add(m.group(1))

    for key in ("photoId", "mediaId", "googlePhotoId", "id"):
        v = deep_find_first_string_key(js, {key})
        if v and len(v) >= 10 and "http" not in v:
            ids.add(v)

    return sorted(ids)


def extract_people(js: dict) -> list[str]:
    people: list[str] = []
    raw = js.get("people")
    if isinstance(raw, list):
        for p in raw:
            if isinstance(p, dict):
                name = p.get("name")
                if isinstance(name, str) and name.strip():
                    people.append(name.strip())
    return sorted(set(people))


def extract_geo(js: dict) -> Optional[dict]:
    g = js.get("geoData")
    if isinstance(g, dict):
        out: dict[str, Any] = {}
        for k in ("latitude", "longitude", "altitude", "latitudeSpan", "longitudeSpan"):
            v = g.get(k)
            out[k] = v if isinstance(v, (int, float)) else None
        if all(out[k] is None for k in out):
            return None
        return out
    return None


def canonical_media_path(sha: str, ext: str) -> str:
    return os.path.join(CANON, f"{sha}{ext}")


def sidecar_path(sha: str, ext: str) -> str:
    return os.path.join(CANON, f"{sha}{ext}.shafferography.json")


unique_by_sha: dict[str, dict] = {}
with open(UNIQUE_CSV, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        unique_by_sha[row["sha256"]] = row

occurrences: dict[str, list[dict]] = defaultdict(list)


def add_occ(row: dict) -> None:
    occurrences[row["sha256"]].append(row)


with open(UNIQUE_CSV, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        add_occ(row)

if os.path.isfile(DUP_CSV):
    with open(DUP_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            add_occ(row)

written = 0
skipped_missing_media = 0
missing_json = 0

for sha, uniq in unique_by_sha.items():
    ext = (uniq.get("ext") or "").strip().lower()
    if not ext:
        continue
    if not ext.startswith("."):
        ext = "." + ext

    canon_media = canonical_media_path(sha, ext)
    if not os.path.isfile(canon_media):
        skipped_missing_media += 1
        continue

    google_ids: set[str] = set()
    people: set[str] = set()
    geo_choice: Optional[dict] = None

    occs = occurrences.get(sha, [])
    occs_sorted = sorted(
        occs,
        key=lambda r: (
            0 if r.get("absPath") == uniq.get("absPath") else 1,
            r.get("account", ""),
            r.get("relativePath", ""),
        ),
    )

    any_json = False
    for occ in occs_sorted:
        meta_path = find_takeout_metadata_json(occ.get("absPath", ""))
        if not meta_path:
            continue
        any_json = True
        try:
            with open(meta_path, "r", encoding="utf-8") as jf:
                js = json.load(jf)
        except Exception:
            continue

        for gid in extract_google_photo_ids(js):
            google_ids.add(gid)
        for nm in extract_people(js):
            people.add(nm)

        if geo_choice is None:
            g = extract_geo(js)
            if g is not None:
                geo_choice = g

    if not any_json:
        missing_json += 1

    original_filename = os.path.basename(uniq["absPath"])
    original_takeout_path = os.path.join(
        "GOOGLE_TAKEOUT", uniq["account"], "unzipped", uniq["relativePath"]
    )

    meta_abs = find_takeout_metadata_json(uniq["absPath"])
    original_meta_path = ""
    if meta_abs:
        try:
            original_meta_path = os.path.relpath(meta_abs, PHOTO_ARCHIVE)
        except Exception:
            original_meta_path = meta_abs

    google_ids_sorted = sorted(google_ids)
    primary_google_id = google_ids_sorted[0] if google_ids_sorted else ""

    sidecar = {
        "version": 1,
        "source": {
            "system": "google-photos-takeout",
            "googlePhotoIds": google_ids_sorted,
            "googlePhotoId": primary_google_id,
        },
        "provenance": {
            "takeoutBatchId": TAKEOUT_BATCH_ID,
            "importedAt": now_utc_iso(),
            "ingestTool": INGEST_TOOL,
        },
        "original": {
            "filename": original_filename,
            "takeoutPath": original_takeout_path,
            "metadataPath": original_meta_path,
        },
        "people": sorted(people),
        "geoData": geo_choice,
    }

    out_path = sidecar_path(sha, ext)
    with open(out_path, "w", encoding="utf-8") as out:
        json.dump(sidecar, out, ensure_ascii=False, indent=2)
        out.write("\n")
    written += 1

print(f"Run label: {RUN_LABEL}")
print(f"Sidecars written: {written:,}")
print(f"Skipped (missing canonical media): {skipped_missing_media:,}")
print(f"Canonicals with no metadata JSON found: {missing_json:,}")
