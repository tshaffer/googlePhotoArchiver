import os, json, hashlib
from pathlib import Path
from datetime import datetime, timezone

def require_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"ERROR: env var {name} is required")
    return v
  
PHOTO_ARCHIVE = require_env("PHOTO_ARCHIVE")
ACCOUNTS = require_env("ACCOUNTS_STR").split()
TAKEOUT_ROOT = os.path.join(PHOTO_ARCHIVE, "GOOGLE_TAKEOUT")
CANON = require_env("CANON")
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
