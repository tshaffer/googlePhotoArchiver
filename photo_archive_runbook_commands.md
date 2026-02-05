# PHOTO_ARCHIVE – Runbook Commands (One-time + Per-Run)

This document is **reference documentation**: a step-by-step set of commands to build and maintain `PHOTO_ARCHIVE/` using Google Photos Takeout, producing:

- `CANONICAL/by-hash/` (immutable media bytes)
- `MANIFESTS/runs/<RUN_LABEL>/` (audit + provenance per run)
- `VIEWS/*` (regenerable symlink views)

The commands are written so you can set **shell parameters** for each dedupe iteration.

> Assumptions
> - macOS + zsh
> - `python3` available
> - `exiftool` available (optional but recommended for EXIF-based views)
> - You run these from a terminal (iTerm, Terminal.app)

---

## 0) Conventions

- **Never modify** anything under `CANONICAL/` or `GOOGLE_TAKEOUT/` once created.
- Treat `VIEWS/` as disposable.
- Manifests are small, but **must** be backed up.
- Prefer running the **versioned scripts** in `PHOTO_SCRIPTS` (instead of inline Python one-offs).

---

## 1) One-time setup (run once per archive)

### 1.1 Set base paths

```bash
# REQUIRED: where the archive lives
export PHOTO_ARCHIVE="/Volumes/ShMedia/PHOTO_ARCHIVE"

# REQUIRED: repo containing the pipeline scripts
export PHOTO_SCRIPTS="$HOME/Documents/Projects/photo-scripts"   # <-- change

# Canonical directory
export CANON="$PHOTO_ARCHIVE/CANONICAL/by-hash"
```

### 1.2 Create the directory skeleton

```bash
mkdir -p "$PHOTO_ARCHIVE"/{CANONICAL/by-hash,GOOGLE_TAKEOUT,MANIFESTS/runs,MANIFESTS/latest,VIEWS,DEDUP_WORK,INBOX,LOGS}

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

### 1.3 Python import setup (required for PHOTO_SCRIPTS)

```bash
export PYTHONPATH="$PHOTO_SCRIPTS"
```

### 1.4 Optional: install tools

```bash
# exiftool (for EXIF-based views)
# brew install exiftool
```

---

## 2) Per-run setup (do this each time you ingest new Takeouts)

### 2.1 Define run parameters

```bash
# A label to isolate manifests/logs for this run (strongly recommended)
export RUN_LABEL="$(date +%Y-%m-%d_%H_%M)__takeout_ingest"

# zsh-native array (used by loops)
ACCOUNTS=(shafferFamily shafferFamilyPhotosTLSJR)

# exported scalar (used by Python)
export ACCOUNTS_STR="${ACCOUNTS[*]}"

# Which account is preferred when identical bytes appear in more than one account
# NOTE: policy for THIS run only
export PREFERRED_ACCOUNT="shafferFamilyPhotosTLSJR"

# Per-account: where the takeout ZIPs currently live (can change per run)
export ZIP_SRC_shafferFamily="/Users/tedshaffer/Downloads/ShafferFamilyDedupeTakeouts"
export ZIP_SRC_shafferFamilyPhotosTLSJR="/Users/tedshaffer/Downloads/ShafferFamilyPhotosTLSJRDedupeTakeouts"

# Per-run log
export RUN_LOG="$PHOTO_ARCHIVE/LOGS/${RUN_LABEL}.log"

echo "RUN_LABEL=$RUN_LABEL" | tee -a "$RUN_LOG"
echo "ACCOUNTS=${ACCOUNTS[*]}" | tee -a "$RUN_LOG"
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

Supports **multiple ZIPs per account** (copy whole folder).

```bash
set -euo pipefail

for acct in "${ACCOUNTS[@]}"; do
  src_var="ZIP_SRC_${acct}"
  src_dir="${(P)src_var}"

  echo "Copying ZIPs for $acct from: $src_dir" | tee -a "$RUN_LOG"
  rsync -aAXhv --info=progress2 --exclude="._*" --exclude=".DS_Store"     "$src_dir/"     "$PHOTO_ARCHIVE/GOOGLE_TAKEOUT/$acct/zips/"     | tee -a "$RUN_LOG"
done
```

### 3.2 Unzip all staged ZIPs

Each ZIP expands to `unzipped/<zip-stem>/...` so ZIPs don’t collide.

```bash
set -euo pipefail

for acct in "${ACCOUNTS[@]}"; do
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

## 4) Run the pipeline scripts (preferred)

This is the **current** recommended way (matches your `pipeline.sh` style).

### 4.1 Optional run metadata (sidecars)

```bash
# Defaults to RUN_LABEL if omitted, but explicit is nice
export TAKEOUT_BATCH_ID="$RUN_LABEL"
export INGEST_TOOL="dedupe-pipeline"
```

### 4.2 Run the standard pipeline

```bash
set -euo pipefail

python3 "$PHOTO_SCRIPTS/scripts/build_run_plan.py"              | tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/materialize_canonicals.py"      | tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/write_sidecars_from_takeout.py" | tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/canonical_inventory.py"         | tee -a "$RUN_LOG"
```

**Where outputs go:** scripts should write run-isolated artifacts to:

- `MANIFESTS/runs/<RUN_LABEL>/...` (authoritative)
- optionally also update `MANIFESTS/latest/` as convenience pointers

If any script still writes to `MANIFESTS/*.csv` directly, update it to write into the run folder.

---

## 5) Build views (optional, regenerable)

If you have `PHOTO_SCRIPTS` scripts for views, prefer those. If not, the legacy one-off view builders can still be used.

### 5.1 EXIF-based date view (uses exiftool)

Target: `VIEWS/by-date/YYYY/MM/YYYY-MM-DD/` plus `VIEWS/by-date/NO_EXIF/`.

(If you want this as a script in `PHOTO_SCRIPTS/scripts/`, move the legacy block into a file like `build_view_by_exif_date.py`.)

### 5.2 Takeout-JSON-based date view

Target: `VIEWS/by-date-takeout/YYYY/MM/YYYY-MM-DD/` based on `.supplemental-metadata.json`.

(As above, best as a script in `PHOTO_SCRIPTS/scripts/`.)

---

## 6) Back up canonicals (per run)

Example to a single external target:

```bash
export CANON_BACKUP_DEST="/Volumes/SHAFFEROTO/PHOTO_ARCHIVE_CANONICAL"
mkdir -p "$CANON_BACKUP_DEST"

rsync -aHhv --info=progress2 --itemize-changes   --exclude="._*" --exclude=".DS_Store"   "$PHOTO_ARCHIVE/CANONICAL/"   "$CANON_BACKUP_DEST/"   | tee -a "$RUN_LOG"
```

Also back up manifests:

```bash
export MANIFESTS_BACKUP_DEST="/Volumes/SHAFFEROTO/PHOTO_ARCHIVE_MANIFESTS"
mkdir -p "$MANIFESTS_BACKUP_DEST"

rsync -aHhv --info=progress2 --itemize-changes   --exclude="._*" --exclude=".DS_Store"   "$PHOTO_ARCHIVE/MANIFESTS/"   "$MANIFESTS_BACKUP_DEST/"   | tee -a "$RUN_LOG"
```

---

## 7) Quick sanity checks

```bash
# Count canonical media (exclude sidecars)
find "$PHOTO_ARCHIVE/CANONICAL/by-hash" -type f ! -name "*.shafferography.json" | wc -l

# Count sidecars
find "$PHOTO_ARCHIVE/CANONICAL/by-hash" -type f -name "*.shafferography.json" | wc -l

# Count EXIF view symlinks
find "$PHOTO_ARCHIVE/VIEWS/by-date" -type l | wc -l
```

---

## 8) Notes for future refinement

- Make *all* manifest filenames run-isolated under `MANIFESTS/runs/<RUN_LABEL>/`.
- Treat `MANIFESTS/latest/` as a convenience layer only (symlinks or copies).
- If Takeout JSON formats vary, extend `write_sidecars_from_takeout.py` to support additional patterns.
- Consider adding an integrity check script that verifies:
  - filename sha matches computed sha
  - sidecar sha+ext exists
  - inventory matches current directory state

---

End of document.
