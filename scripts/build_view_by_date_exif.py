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

