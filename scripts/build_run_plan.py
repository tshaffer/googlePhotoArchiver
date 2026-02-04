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
