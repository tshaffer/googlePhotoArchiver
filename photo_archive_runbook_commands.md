# PHOTO_ARCHIVE – Runbook Commands (One-time + Per-Run)

This document is **reference documentation**: a step-by-step set of commands to build and maintain `PHOTO_ARCHIVE/` using Google Photos Takeout, producing:
- `CANONICAL/by-hash` (immutable)
- `MANIFESTS/*` (audit + provenance)
- `VIEWS/*` (regenerable symlink views)

The commands are written so you can set **shell parameters** for each dedupe iteration.

> Assumptions
> - macOS + zsh
> - `python3` available
> - `exiftool` available (optional but recommended for EXIF-based view)
> - You will run these from a terminal (iTerm, Terminal.app)

---

## 0) Conventions

- **Never modify** anything under `CANONICAL/` or `GOOGLE_TAKEOUT/` once created.
- Treat `VIEWS/` as disposable.
- Manifests are small, but **must** be backed up.

---

## 1) One-time setup (run once per archive)

### 1.1 Set base paths (edit once)

```bash
# REQUIRED: where the archive lives
export PHOTO_ARCHIVE="/Volumes/ShMedia/PHOTO_ARCHIVE"

# OPTIONAL: where you keep scripts for this archive
export PA_SCRIPTS="$PHOTO_ARCHIVE/scripts"
```

### 1.2 Create the directory skeleton

```bash
mkdir -p "$PHOTO_ARCHIVE"/{CANONICAL/by-hash,GOOGLE_TAKEOUT,MANIFESTS,VIEWS,DEDUP_WORK,INBOX,LOGS}

# Canonical invariants doc (safe to re-run)
cat > "$PHOTO_ARCHIVE/CANONICAL/README_CANONICAL.md" <<'EOF'
# PHOTO_ARCHIVE – Canonical Store (by-hash)

- Identity is SHA-256 (content-addressed)
- Canonical filenames: <sha256><ext>
- Files in CANONICAL/by-hash are immutable:
  - Do not rename
  - Do not edit in place (including EXIF)
  - Do not delete except via audited process

Views are symlinks under PHOTO_ARCHIVE/VIEWS and are regenerable.
EOF
```

### 1.3 Optional: install tools

```bash
# exiftool (for EXIF-based views)
# brew install exiftool

# (Optional) GNU coreutils for gdate, etc.
# brew install coreutils
```

### 1.4 Helper: create a log file for each run

```bash
mkdir -p "$PHOTO_ARCHIVE/LOGS"
```

---

## 2) Per-run setup (do this each time you ingest new Takeouts)

### 2.1 Define run parameters

Set these **for this dedupe iteration**.

```bash
# A label to group logs/manifests for this run
export RUN_LABEL="$(date +%Y-%m-%d_%H_%M)__takeout_ingest"

# zsh-native array (used by shell loops)
ACCOUNTS=(shafferFamily shafferFamilyPhotosTLSJR)

# exported scalar (used by Python)
export ACCOUNTS_STR="${ACCOUNTS[*]}"

# Per-account: where the takeout ZIPs currently live (you can change these per run)
export ZIP_SRC_shafferFamily="/Users/tedshaffer/Downloads/ShafferFamilyDedupeTakeouts"
export ZIP_SRC_shafferFamilyPhotosTLSJR="/Users/tedshaffer/Downloads/ShafferFamilyPhotosTLSJRDedupeTakeouts"

# Which account is preferred when identical bytes appear in more than one account
# NOTE: this is policy *for this run*, not forever.
export PREFERRED_ACCOUNT="shafferFamilyPhotosTLSJR"

# Canonical directory
export CANON="$PHOTO_ARCHIVE/CANONICAL/by-hash"

# Log file
export RUN_LOG="$PHOTO_ARCHIVE/LOGS/${RUN_LABEL}.log"

echo "RUN_LABEL=$RUN_LABEL" | tee -a "$RUN_LOG"
echo "ACCOUNTS=$ACCOUNTS" | tee -a "$RUN_LOG"
echo "PREFERRED_ACCOUNT=$PREFERRED_ACCOUNT" | tee -a "$RUN_LOG"
```

### 2.2 Create per-account takeout staging directories

```bash
for acct in "${ACCOUNTS[@]}"; do
  mkdir -p "$PHOTO_ARCHIVE/GOOGLE_TAKEOUT/$acct"/{zips,unzipped}
done
```

---

## 3) Stage Takeouts (copy ZIPs + unzip)

### 3.1 Copy ZIPs into the archive (provenance preserved)

This copies ZIP files from your downloads folders into the archive.

```bash
set -e

for acct in "${ACCOUNTS[@]}"; do
  src_var="ZIP_SRC_${acct}"
  src_dir="${(P)src_var}"

  echo "Copying ZIPs for $acct from: $src_dir" | tee -a "$RUN_LOG"

  rsync -aAXhv --info=progress2 --exclude="._*" --exclude=".DS_Store" "$src_dir/" "$PHOTO_ARCHIVE/GOOGLE_TAKEOUT/$acct/zips/" | tee -a "$RUN_LOG"
done
```

> If you prefer a *manual* list of ZIP paths instead of copying whole directories, use explicit `cp` commands.

### 3.2 Unzip all staged ZIPs

```bash
set -e

for acct in $ACCOUNTS; do
  unzip_root="$PHOTO_ARCHIVE/GOOGLE_TAKEOUT/$acct/unzipped"
  mkdir -p "$unzip_root"

  echo "Unzipping for $acct ..." | tee -a "$RUN_LOG"

  for z in "$PHOTO_ARCHIVE/GOOGLE_TAKEOUT/$acct/zips"/*.zip(.N); do
    base="$(basename "$z" .zip)"
    dest="$unzip_root/$base"
    if [[ -d "$dest" ]]; then
      echo "  SKIP (already unzipped): $dest" | tee -a "$RUN_LOG"
    else
      echo "  unzip -> $dest" | tee -a "$RUN_LOG"
      mkdir -p "$dest"
      unzip -q "$z" -d "$dest"
    fi
  done

done
```

---

## 4) Build dedup plan (hash everything, choose canonicals)

This step:
- walks all media files under all unzipped Takeouts
- computes SHA-256
- assigns each file to `unique` vs `duplicate`
- applies `PREFERRED_ACCOUNT` when the same hash appears in multiple accounts

It writes two manifests in `MANIFESTS/`:
- `dedup_plan__unique.csv`
- `dedup_plan__duplicates.csv`

### 4.1 Run plan builder

```bash
python3 - <<'PY'
import os, csv, hashlib
from pathlib import Path
from collections import defaultdict

PHOTO_ARCHIVE = os.environ["PHOTO_ARCHIVE"]
ACCOUNTS = os.environ["ACCOUNTS_STR"].split()
PREFERRED_ACCOUNT = os.environ["PREFERRED_ACCOUNT"]
RUN_LABEL = os.environ.get("RUN_LABEL", "run")

TAKEOUT_ROOT = os.path.join(PHOTO_ARCHIVE, "GOOGLE_TAKEOUT")
OUT_DIR = os.path.join(PHOTO_ARCHIVE, "MANIFESTS")
os.makedirs(OUT_DIR, exist_ok=True)

UNIQUE_CSV = os.path.join(OUT_DIR, "dedup_plan__unique.csv")
DUP_CSV = os.path.join(OUT_DIR, "dedup_plan__duplicates.csv")

MEDIA_EXTS = {
  ".jpg",".jpeg",".png",".gif",".heic",".tif",".tiff",
  ".mp4",".mov",".m4v",".avi",".3gp",".mpg",".mpeg",".webm"
}

def is_media(p: str) -> bool:
  return Path(p).suffix.lower() in MEDIA_EXTS

def sha256_file(path: str, chunk_size: int = 8*1024*1024) -> str:
  h = hashlib.sha256()
  with open(path, "rb") as f:
    while True:
      b = f.read(chunk_size)
      if not b:
        break
      h.update(b)
  return h.hexdigest()

# Gather all media candidates
records_by_sha = defaultdict(list)
scanned = 0

for acct in ACCOUNTS:
  base = os.path.join(TAKEOUT_ROOT, acct, "unzipped")
  if not os.path.isdir(base):
    continue
  for dirpath, _, filenames in os.walk(base):
    for fn in filenames:
      if fn.startswith("._"):
        continue
      p = os.path.join(dirpath, fn)
      if not is_media(p):
        continue
      scanned += 1
      sha = sha256_file(p)
      rel = os.path.relpath(p, base)
      records_by_sha[sha].append({
        "account": acct,
        "takeoutRoot": base,
        "relativePath": rel,
        "absPath": p,
        "ext": Path(fn).suffix.lower(),
      })

print(f"Scanned media files: {scanned:,}")
print(f"Unique hashes found: {len(records_by_sha):,}")

# Choose canonical per sha
unique_rows = []
dup_rows = []

for sha, recs in records_by_sha.items():
  # Sort so preferred account wins; otherwise stable fallback
  recs_sorted = sorted(
    recs,
    key=lambda r: (
      0 if r["account"] == PREFERRED_ACCOUNT else 1,
      r["account"],
      r["relativePath"],
    ),
  )
  canonical = recs_sorted[0]

  unique_rows.append({
    "sha256": sha,
    "ext": canonical["ext"],
    "account": canonical["account"],
    "relativePath": canonical["relativePath"],
    "absPath": canonical["absPath"],
    "runLabel": RUN_LABEL,
    "preferredAccount": PREFERRED_ACCOUNT,
    "occurrences": str(len(recs)),
  })

  for r in recs_sorted[1:]:
    dup_rows.append({
      "sha256": sha,
      "ext": r["ext"],
      "account": r["account"],
      "relativePath": r["relativePath"],
      "absPath": r["absPath"],
      "runLabel": RUN_LABEL,
      "preferredAccount": PREFERRED_ACCOUNT,
    })

# Write CSVs
unique_rows.sort(key=lambda r: r["sha256"])
dup_rows.sort(key=lambda r: (r["sha256"], r["account"], r["relativePath"]))

with open(UNIQUE_CSV, "w", newline="", encoding="utf-8") as f:
  w = csv.DictWriter(f, fieldnames=list(unique_rows[0].keys()) if unique_rows else [
    "sha256","ext","account","relativePath","absPath","runLabel","preferredAccount","occurrences"
  ])
  w.writeheader()
  w.writerows(unique_rows)

with open(DUP_CSV, "w", newline="", encoding="utf-8") as f:
  w = csv.DictWriter(f, fieldnames=list(dup_rows[0].keys()) if dup_rows else [
    "sha256","ext","account","relativePath","absPath","runLabel","preferredAccount"
  ])
  w.writeheader()
  w.writerows(dup_rows)

print(f"Wrote: {UNIQUE_CSV} ({len(unique_rows):,} rows)")
print(f"Wrote: {DUP_CSV} ({len(dup_rows):,} rows)")
PY
```

---

## 5) Apply dedup plan (materialize canonicals)

This step is where **previously imported photos are skipped**:
- If `CANONICAL/by-hash/<sha><ext>` already exists, we do not copy it again.

### 5.1 Materialize canonicals

```bash
python3 - <<'PY'
import os, csv, shutil

PHOTO_ARCHIVE = os.environ["PHOTO_ARCHIVE"]
CANON = os.environ["CANON"]

UNIQUE_CSV = os.path.join(PHOTO_ARCHIVE, "MANIFESTS", "dedup_plan__unique.csv")
os.makedirs(CANON, exist_ok=True)

copied = 0
skipped = 0

with open(UNIQUE_CSV, newline="", encoding="utf-8") as f:
  r = csv.DictReader(f)
  for row in r:
    sha = row["sha256"]
    ext = row["ext"]
    src = row["absPath"]
    dest = os.path.join(CANON, f"{sha}{ext}")

    if os.path.exists(dest):
      skipped += 1
      continue

    # Copy bytes exactly; do not modify metadata
    shutil.copy2(src, dest)
    copied += 1

print(f"Copied new canonicals: {copied:,}")
print(f"Skipped (already present): {skipped:,}")
print("Done.")
PY
```


### 5.2 Generate per-canonical metadata sidecars (Google Takeout enrichment)

This step reads the dedup manifests and Takeout metadata JSON files and writes a **per-canonical sidecar**
next to each canonical media file:

```
CANONICAL/by-hash/<sha256><ext>.shafferography.json
```

It persists (v1 contract):
- `source.googlePhotoIds[]` (array)
- `provenance`
- `original filename/path`
- `googleTakeout.people[]`
- `googleTakeout.geoData`

> We intentionally do **not** merge `geoData` into EXIF here. That decision is deferred to Shafferography import.

#### 5.2.1 Set run metadata parameters

```bash
# REQUIRED: identify this takeout ingestion batch (used in provenance)
export TAKEOUT_BATCH_ID="$RUN_LABEL"

# OPTIONAL: label the tool/version writing sidecars
export INGEST_TOOL="dedupe-pipeline"
```

#### 5.2.2 Write sidecars from manifests + Takeout JSON

```bash
python3 - <<'PY'
import os, csv, json, re
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

PHOTO_ARCHIVE = os.environ["PHOTO_ARCHIVE"]
CANON = os.environ["CANON"]
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
PY
```


---

## 6) Canonical inventory (audit/tripwire)

```bash
python3 - <<'PY'
import os, csv
from datetime import datetime

PHOTO_ARCHIVE = os.environ["PHOTO_ARCHIVE"]
CANON = os.environ["CANON"]
OUT = os.path.join(PHOTO_ARCHIVE, "MANIFESTS", "canonical_inventory__by-hash.csv")

rows = []
generated = datetime.utcnow().isoformat(timespec="seconds") + "Z"

for fn in os.listdir(CANON):
  p = os.path.join(CANON, fn)
  if not os.path.isfile(p):
    continue
  st = os.stat(p)
  sha, ext = os.path.splitext(fn)
  rows.append({
    "generatedAtUtc": generated,
    "sha256": sha,
    "ext": ext.lower(),
    "bytes": st.st_size,
    "mtimeEpochSec": int(st.st_mtime),
    "fileName": fn,
  })

rows.sort(key=lambda r: r["sha256"])
os.makedirs(os.path.dirname(OUT), exist_ok=True)

with open(OUT, "w", newline="", encoding="utf-8") as f:
  w = csv.DictWriter(f, fieldnames=["generatedAtUtc","sha256","ext","bytes","mtimeEpochSec","fileName"])
  w.writeheader()
  w.writerows(rows)

print(f"Wrote {len(rows):,} rows -> {OUT}")
PY
```

---

## 7) Build views (optional, regenerable)

### 7.1 EXIF-based date view (uses exiftool)

Creates symlinks:
- `VIEWS/by-date/YYYY/MM/YYYY-MM-DD/` based on EXIF dates
- `VIEWS/by-date/NO_EXIF/...` fallback bucket

```bash
python3 - <<'PY'
import os, re, subprocess
from pathlib import Path
from collections import defaultdict

PHOTO_ARCHIVE = os.environ["PHOTO_ARCHIVE"]
CANON = os.environ["CANON"]
VIEW_ROOT = os.path.join(PHOTO_ARCHIVE, "VIEWS", "by-date")

os.makedirs(VIEW_ROOT, exist_ok=True)

rx = re.compile(r"^(\d{4}):(\d{2}):(\d{2})\b")

created = 0
no_exif = 0
skipped = 0

for fn in os.listdir(CANON):
  # Skip non-media artifacts (macOS + our pipeline sidecars)
  if fn.startswith("._") or fn == ".DS_Store" or fn.endswith(".shafferography.json"):
    skipped += 1
    continue

  src = os.path.join(CANON, fn)
  if not os.path.isfile(src):
    continue

  # Get DateTimeOriginal/CreateDate for this file
  cmd1 = ["exiftool", "-DateTimeOriginal", "-CreateDate", "-s", "-s", "-s", src]
  p1 = subprocess.run(cmd1, capture_output=True, text=True)
  lines = [ln.strip() for ln in p1.stdout.splitlines() if ln.strip()]

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
PY
```

### 7.2 Takeout-JSON-based date view (supplemental metadata)

Creates symlinks:
- `VIEWS/by-date-takeout/YYYY/MM/YYYY-MM-DD/` based on Takeout `.supplemental-metadata.json`

```bash
python3 - <<'PY'
import os, json, hashlib
from pathlib import Path
from datetime import datetime, timezone

PHOTO_ARCHIVE = os.environ["PHOTO_ARCHIVE"]
ACCOUNTS = os.environ["ACCOUNTS_STR"].split()
TAKEOUT_ROOT = os.path.join(PHOTO_ARCHIVE, "GOOGLE_TAKEOUT")
CANON = os.environ["CANON"]
VIEW_ROOT = os.path.join(PHOTO_ARCHIVE, "VIEWS", "by-date-takeout")

MEDIA_EXTS = {
  ".jpg",".jpeg",".png",".gif",".heic",".tif",".tiff",
  ".mp4",".mov",".m4v",".avi",".3gp",".mpg",".mpeg",".webm"
}

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

def canon_path_for_sha(sha: str):
  # filenames are sha+ext; find match
  for fn in os.listdir(CANON):
    if fn.startswith("._") or fn == ".DS_Store" or fn.endswith(".json"):
      continue
    if fn.startswith(sha):
      return os.path.join(CANON, fn)
  return None

# Load canonical hashes (skip non-media artifacts and sidecars)
canon_hashes = set()
for fn in os.listdir(CANON):
  if fn.startswith("._") or fn == ".DS_Store" or fn.endswith(".json"):
    continue
  p = os.path.join(CANON, fn)
  if os.path.isfile(p):
    sha, _ = os.path.splitext(fn)
    canon_hashes.add(sha)

# Build index of supplemental metadata JSON: (dirpath, media_filename_lower) -> timestamp
index = {}
json_scanned = 0

for acct in ACCOUNTS:
  base = os.path.join(TAKEOUT_ROOT, acct, "unzipped")
  if not os.path.isdir(base):
    continue
  for dirpath, _, filenames in os.walk(base):
    for fn in filenames:
      if fn.startswith("._") or fn == ".DS_Store":
        continue
      if not fn.lower().endswith(".supplemental-metadata.json"):
        continue

      json_scanned += 1
      json_path = os.path.join(dirpath, fn)
      media_name = fn[:-len(".supplemental-metadata.json")]
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
      if fn.startswith("._") or fn == ".DS_Store":
        continue
      media_path = os.path.join(dirpath, fn)
      if not is_media(media_path):
        continue

      sha = sha256_file(media_path)
      if sha not in canon_hashes:
        continue

      key = (dirpath, norm(fn))
      ts = index.get(key)
      if ts is None:
        no_json_match += 1
        continue

      canon_src = canon_path_for_sha(sha)
      if not canon_src:
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

print(f"Supplemental JSON scanned: {json_scanned:,}")
print(f"Matched canonical items to JSON dates: {matched_to_json:,}")
print(f"No supplemental JSON match (folder+filename): {no_json_match:,}")
print(f"Created symlinks: {created:,}")
print("Done.")
PY
```

---

## 8) Back up canonicals (per run)

Example to a single external target:

```bash
export CANON_BACKUP_DEST="/Volumes/SHAFFEROTO/PHOTO_ARCHIVE_CANONICAL"
mkdir -p "$CANON_BACKUP_DEST"

rsync -aHhv --info=progress2 --itemize-changes \
  --exclude="._*" --exclude=".DS_Store" \
  "$PHOTO_ARCHIVE/CANONICAL/" \
  "$CANON_BACKUP_DEST/" \
  | tee -a "$RUN_LOG"
```

---

## 9) Quick sanity checks

```bash
# Count canonicals
find "$PHOTO_ARCHIVE/CANONICAL/by-hash" -type f | wc -l

# Count EXIF view symlinks (should match canonical count if built from canonicals)
find "$PHOTO_ARCHIVE/VIEWS/by-date" -type l | wc -l

# Verify takeout view includes older years (if present)
ls "$PHOTO_ARCHIVE/VIEWS/by-date-takeout" | head -20
```

---

## 10) Notes for future refinement

- The Takeout JSON view currently uses `.supplemental-metadata.json` files. Some Takeout exports include other JSON formats; you can extend the indexer if needed.
- If you want per-run isolation, rename manifest outputs to include `RUN_LABEL`. (Current commands overwrite the main manifest filenames.)

