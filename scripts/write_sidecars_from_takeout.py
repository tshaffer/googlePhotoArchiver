import os, csv, json, re
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

def require_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"ERROR: env var {name} is required")
    return v
  
PHOTO_ARCHIVE = require_env("PHOTO_ARCHIVE")
CANON = require_env("CANON")
TAKEOUT_BATCH_ID = os.environ.get("TAKEOUT_BATCH_ID", os.environ.get("RUN_LABEL", "unknown-batch"))
INGEST_TOOL = os.environ.get("INGEST_TOOL", "dedupe-pipeline")

UNIQUE_CSV = os.path.join(PHOTO_ARCHIVE, "MANIFESTS", "dedup_plan__unique.csv")
DUP_CSV = os.path.join(PHOTO_ARCHIVE, "MANIFESTS", "dedup_plan__duplicates.csv")

# ---- helpers ---------------------------------------------------------------

PHOTO_URL_RX = re.compile(r"/photo/([^/?#]+)")

def now_utc_iso():
  return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def first_non_null(*vals):
  for v in vals:
    if v is not None:
      return v
  return None

def find_takeout_metadata_json(media_abs_path: str):
  """Try to find the Takeout JSON sidecar for a media file."""
  p = Path(media_abs_path)

  # Common Takeout formats:
  #   IMG_1234.JPG.json
  #   IMG_1234.JPG.supplemental-metadata.json
  cand1 = str(p) + ".json"
  cand2 = str(p) + ".supplemental-metadata.json"

  if os.path.isfile(cand1):
    return cand1
  if os.path.isfile(cand2):
    return cand2

  # Some takeouts store the json as "<name>.supplemental-metadata.json" *without* including the media extension.
  # Example: "IMG_1234.supplemental-metadata.json"
  cand3 = str(p.with_suffix("")) + ".supplemental-metadata.json"
  if os.path.isfile(cand3):
    return cand3

  return None

def deep_find_first_string_key(obj, keys):
  """Search nested dict/list for first string value under any key in keys."""
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

def extract_google_photo_ids(js: dict):
  ids = set()

  url = js.get("url")
  if isinstance(url, str):
    m = PHOTO_URL_RX.search(url)
    if m:
      ids.add(m.group(1))

  # Some exports may include explicit id keys (varies by format)
  # We try a conservative nested search.
  for key in ("photoId", "mediaId", "googlePhotoId", "id"):
    v = deep_find_first_string_key(js, {key})
    if v and len(v) >= 10 and "http" not in v:
      # avoid accidentally capturing URLs
      ids.add(v)

  return sorted(ids)

def extract_people(js: dict):
  people = []
  raw = js.get("people")
  if isinstance(raw, list):
    for p in raw:
      if isinstance(p, dict):
        name = p.get("name")
        if isinstance(name, str) and name.strip():
          people.append(name.strip())
  # de-dupe preserving case, stable sort for determinism
  return sorted(set(people))

def extract_geo(js: dict):
  g = js.get("geoData")
  if isinstance(g, dict):
    # Keep verbatim numeric fields if present
    out = {}
    for k in ("latitude","longitude","altitude","latitudeSpan","longitudeSpan"):
      v = g.get(k)
      out[k] = v if isinstance(v, (int, float)) else None
    # If all are None, treat as missing
    if all(out[k] is None for k in out):
      return None
    return out
  return None

def canonical_media_path(sha: str, ext: str):
  return os.path.join(CANON, f"{sha}{ext}")

def sidecar_path(sha: str, ext: str):
  return os.path.join(CANON, f"{sha}{ext}.shafferography.json")

# ---- load manifests --------------------------------------------------------

unique_by_sha = {}
with open(UNIQUE_CSV, newline="", encoding="utf-8") as f:
  for row in csv.DictReader(f):
    unique_by_sha[row["sha256"]] = row

occurrences = defaultdict(list)

def add_occ(row):
  occurrences[row["sha256"]].append(row)

with open(UNIQUE_CSV, newline="", encoding="utf-8") as f:
  for row in csv.DictReader(f):
    add_occ(row)

if os.path.isfile(DUP_CSV):
  with open(DUP_CSV, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
      add_occ(row)

# ---- build sidecars --------------------------------------------------------

written = 0
skipped_missing_media = 0
missing_json = 0

for sha, uniq in unique_by_sha.items():
  ext = uniq["ext"]
  canon_media = canonical_media_path(sha, ext)
  if not os.path.isfile(canon_media):
    skipped_missing_media += 1
    continue

  google_ids = set()
  people = set()
  geo_choice = None

  # Prefer geo from the canonical chosen occurrence first (if present)
  occs = occurrences.get(sha, [])
  occs_sorted = sorted(
    occs,
    key=lambda r: (
      0 if r.get("absPath") == uniq.get("absPath") else 1,
      r.get("account",""),
      r.get("relativePath",""),
    ),
  )

  for occ in occs_sorted:
    meta_path = find_takeout_metadata_json(occ["absPath"])
    if not meta_path:
      continue
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

  if not google_ids and not people and geo_choice is None:
    # We can still write a minimal sidecar with provenance + original, but track missing JSON
    # Check if any metadata json existed at all
    any_json = False
    for occ in occs_sorted:
      if find_takeout_metadata_json(occ["absPath"]):
        any_json = True
        break
    if not any_json:
      missing_json += 1

  # Build original breadcrumbs from the canonical chosen record
  original_filename = os.path.basename(uniq["absPath"])
  original_takeout_path = os.path.join("GOOGLE_TAKEOUT", uniq["account"], "unzipped", uniq["relativePath"])
  meta_abs = find_takeout_metadata_json(uniq["absPath"])
  original_meta_path = None
  if meta_abs:
    # store as archive-relative
    try:
      original_meta_path = os.path.relpath(meta_abs, PHOTO_ARCHIVE)
    except Exception:
      original_meta_path = meta_abs

  sidecar = {
    "version": 1,
    "source": {
      "system": "google-photos-takeout",
      "googlePhotoIds": sorted(google_ids),
    },
    "provenance": {
      "takeoutBatchId": TAKEOUT_BATCH_ID,
      "importedAt": now_utc_iso(),
      "ingestTool": INGEST_TOOL,
    },
    "original": {
      "filename": original_filename,
      "takeoutPath": original_takeout_path,
      "metadataPath": original_meta_path or "",
    },
    "googleTakeout": {
      "people": sorted(people),
      "geoData": geo_choice,
    },
  }

  out_path = sidecar_path(sha, ext)
  with open(out_path, "w", encoding="utf-8") as out:
    json.dump(sidecar, out, ensure_ascii=False, indent=2)
    out.write("\n")

  written += 1

print(f"Sidecars written: {written:,}")
print(f"Skipped (missing canonical media): {skipped_missing_media:,}")
print(f"Canonicals with no metadata JSON found: {missing_json:,}")
