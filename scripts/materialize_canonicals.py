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
