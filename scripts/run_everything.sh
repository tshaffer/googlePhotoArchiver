#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# 0) CONFIG (edit these for your machine)
###############################################################################

export PHOTO_SCRIPTS="/Users/tedshaffer/Documents/Projects/googlePhotoArchiver"
export PYTHONPATH="$PHOTO_SCRIPTS"

export PHOTO_ARCHIVE="/Volumes/ShMedia/PHOTO_ARCHIVE"
export PREFERRED_ACCOUNT="shafferFamilyPhotosTLSJR"
export ACCOUNTS_STR="shafferFamily shafferFamilyPhotosTLSJR"

# Where canonicals live (your pipeline uses this)
export CANON="$PHOTO_ARCHIVE/CANONICAL/by-hash"

# Run identity (used for logs + provenance)
export RUN_LABEL="$(date +%Y-%m-%d_%H_%M)__takeout_ingest"
export RUN_LOG="$PHOTO_ARCHIVE/LOGS/${RUN_LABEL}.log"

# Takeout batch/provenance defaults (used by write_sidecars_from_takeout.py)
export TAKEOUT_BATCH_ID="${TAKEOUT_BATCH_ID:-$RUN_LABEL}"
export INGEST_TOOL="${INGEST_TOOL:-dedupe-pipeline}"

# Where ZIPs come from (per account)  <-- YOU ALREADY HAVE THESE
export ZIP_SRC_shafferFamily="/Users/tedshaffer/Downloads/ShafferFamilyDedupeTakeouts"
export ZIP_SRC_shafferFamilyPhotosTLSJR="/Users/tedshaffer/Downloads/ShafferFamilyPhotosTLSJRDedupeTakeouts"

# Canonical backup destination (Step 8)
export CANON_BACKUP_DEST="/Volumes/SHAFFEROTO/PHOTO_ARCHIVE_CANONICAL"

###############################################################################
# 1) HELPERS
###############################################################################

log() {
  mkdir -p "$(dirname "$RUN_LOG")"
  echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$RUN_LOG"
}

require_dir() {
  local d="$1"
  if [[ ! -d "$d" ]]; then
    log "ERROR: required directory missing: $d"
    exit 1
  fi
}

require_file() {
  local f="$1"
  if [[ ! -f "$f" ]]; then
    log "ERROR: required file missing: $f"
    exit 1
  fi
}

###############################################################################
# 2) ONE-TIME / SAFETY: create directory skeleton
###############################################################################

log "Run label: $RUN_LABEL"
log "PHOTO_ARCHIVE: $PHOTO_ARCHIVE"
log "PHOTO_SCRIPTS: $PHOTO_SCRIPTS"
log "ACCOUNTS_STR: $ACCOUNTS_STR"
log "PREFERRED_ACCOUNT: $PREFERRED_ACCOUNT"
log "CANON: $CANON"
log "TAKEOUT_BATCH_ID: $TAKEOUT_BATCH_ID"
log "INGEST_TOOL: $INGEST_TOOL"

mkdir -p "$PHOTO_ARCHIVE/LOGS"
mkdir -p "$PHOTO_ARCHIVE/GOOGLE_TAKEOUT"
mkdir -p "$PHOTO_ARCHIVE/MANIFESTS"
mkdir -p "$CANON"

for acct in $ACCOUNTS_STR; do
  mkdir -p "$PHOTO_ARCHIVE/GOOGLE_TAKEOUT/$acct/zips"
  mkdir -p "$PHOTO_ARCHIVE/GOOGLE_TAKEOUT/$acct/unzipped"
done

###############################################################################
# 3) STAGE TAKEOUTS: copy ZIPs into archive + unzip
###############################################################################

for acct in $ACCOUNTS_STR; do
  src_var="ZIP_SRC_${acct}"
  src_dir="${!src_var:-}"

  if [[ -z "$src_dir" ]]; then
    log "ERROR: $src_var is not set"
    exit 1
  fi
  if [[ ! -d "$src_dir" ]]; then
    log "ERROR: $src_var points to missing dir: $src_dir"
    exit 1
  fi

  dest_zips="$PHOTO_ARCHIVE/GOOGLE_TAKEOUT/$acct/zips"
  dest_unz="$PHOTO_ARCHIVE/GOOGLE_TAKEOUT/$acct/unzipped"

  log "Copying ZIPs for $acct from: $src_dir -> $dest_zips"
  rsync -aAXhv --info=progress2 --exclude="._*" --exclude=".DS_Store" \
    "$src_dir/" \
    "$dest_zips/" \
    | tee -a "$RUN_LOG"

  log "Unzipping ZIPs for $acct into: $dest_unz"
  shopt -s nullglob
  zips=( "$dest_zips"/*.zip )
  shopt -u nullglob

  if [[ ${#zips[@]} -eq 0 ]]; then
    log "WARNING: no ZIP files found in: $dest_zips"
  else
    for z in "${zips[@]}"; do
      log "Unzip: $(basename "$z")"
      unzip -oq "$z" -d "$dest_unz"
    done
  fi
done

# Quick tripwire: ensure unzipped dirs exist (and are non-empty-ish)
missing=0
for acct in $ACCOUNTS_STR; do
  d="$PHOTO_ARCHIVE/GOOGLE_TAKEOUT/$acct/unzipped"
  if [[ ! -d "$d" ]]; then
    log "ERROR: missing expected unzipped takeout dir: $d"
    missing=1
  fi
done
if [[ $missing -ne 0 ]]; then
  exit 1
fi

###############################################################################
# 4) RUN THE PYTHON PIPELINE
###############################################################################

require_file "$PHOTO_SCRIPTS/scripts/run_pipeline_core.sh"
log "Running pipeline core: $PHOTO_SCRIPTS/scripts/run_pipeline_core.sh"
bash "$PHOTO_SCRIPTS/scripts/run_pipeline_core.sh" | tee -a "$RUN_LOG"

###############################################################################
# 5) STEP 8: BACK UP CANONICALS (per run)
###############################################################################

mkdir -p "$CANON_BACKUP_DEST"
log "Backing up CANON to: $CANON_BACKUP_DEST"

# Exclude AppleDouble artifacts so rsync doesn't die on xattr reads
rsync -aAXHv --info=progress2 --itemize-changes \
  --exclude="._*" --exclude=".DS_Store" \
  "$PHOTO_ARCHIVE/CANONICAL/" \
  "$CANON_BACKUP_DEST/" \
  | tee -a "$RUN_LOG"

log "ALL DONE."
log "Log: $RUN_LOG"
