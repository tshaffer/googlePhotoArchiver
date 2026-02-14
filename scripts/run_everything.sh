#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# 0) CONFIG (edit these for your machine)
###############################################################################

export PHOTO_SCRIPTS="/Users/tedshaffer/Documents/Projects/googlePhotoArchiver"
export PYTHONPATH="$PHOTO_SCRIPTS"

export PHOTO_ARCHIVE="/Volumes/ShMedia/PHOTO_ARCHIVE"
# export PREFERRED_ACCOUNT="shafferFamilyPhotosTLSJR"
# export ACCOUNTS_STR="shafferFamily shafferFamilyPhotosTLSJR"
export PREFERRED_ACCOUNT="shafferFamily"
export ACCOUNTS_STR="shafferFamily"

# Where canonicals live (your pipeline uses this)
export CANON="$PHOTO_ARCHIVE/CANONICAL/by-hash"

# Run output root (each ZIP gets its own run directory)
export RUNS_ROOT="${RUNS_ROOT:-$PHOTO_ARCHIVE/RUNS}"

# Takeout batch/provenance defaults (used by write_sidecars_from_takeout.py)
export INGEST_TOOL="${INGEST_TOOL:-dedupe-pipeline}"
USER_TAKEOUT_BATCH_ID="${TAKEOUT_BATCH_ID:-}"

# Where ZIPs come from (per account)
export ZIP_SRC_shafferFamily="/Volumes/ShMedia/Dedupe Takeouts/ShafferFamilyPhotos/ZipSrc"
# export ZIP_SRC_shafferFamilyPhotosTLSJR="/Users/tedshaffer/Downloads/ShafferFamilyPhotosTLSJRDedupeTakeouts"

# Canonical backup destination (Step 8)
export CANON_BACKUP_DEST="/Volumes/SHAFFEROTO/PHOTO_ARCHIVE_CANONICAL"

###############################################################################
# 1) HELPERS
###############################################################################

log() {
  if [[ -n "${RUN_LOG:-}" ]]; then
    mkdir -p "$(dirname "$RUN_LOG")"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$RUN_LOG"
  else
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
  fi
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

mkdir -p "$PHOTO_ARCHIVE/GOOGLE_TAKEOUT"
mkdir -p "$PHOTO_ARCHIVE/MANIFESTS"
mkdir -p "$RUNS_ROOT"
mkdir -p "$CANON"

###############################################################################
# 3) ARG PARSING: ZIP LIST OR OVERRIDE MODE
###############################################################################

force_all="${FORCE_REUNZIP_ALL:-0}"
zips=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all)
      force_all=1
      shift
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "ERROR: unknown option: $1" >&2
      exit 1
      ;;
    *)
      zips+=( "$1" )
      shift
      ;;
  esac
done

if [[ $# -gt 0 ]]; then
  zips+=( "$@" )
fi

if [[ "$force_all" == "1" ]]; then
  zips=()
  for acct in $ACCOUNTS_STR; do
    src_var="ZIP_SRC_${acct}"
    src_dir="${!src_var:-}"

    if [[ -z "$src_dir" ]]; then
      echo "ERROR: $src_var is not set" >&2
      exit 1
    fi
    if [[ ! -d "$src_dir" ]]; then
      echo "ERROR: $src_var points to missing dir: $src_dir" >&2
      exit 1
    fi

    shopt -s nullglob
    found=( "$src_dir"/*.zip )
    shopt -u nullglob
    if [[ ${#found[@]} -gt 0 ]]; then
      zips+=( "${found[@]}" )
    fi
  done

  if [[ ${#zips[@]} -eq 0 ]]; then
    echo "ERROR: override mode enabled but no ZIP files found in configured ZIP_SRC_* dirs" >&2
    exit 1
  fi
fi

if [[ ${#zips[@]} -eq 0 ]]; then
  echo "ERROR: no ZIPs provided. Usage: ./run_everything.sh /path/to/A.zip /path/to/B.zip" >&2
  echo "       Or use --all / FORCE_REUNZIP_ALL=1 to process all ZIPs in ZIP_SRC_* dirs." >&2
  exit 1
fi

for z in "${zips[@]}"; do
  if [[ ! -f "$z" ]]; then
    echo "ERROR: ZIP not found: $z" >&2
    exit 1
  fi
done

###############################################################################
# 4) ONE RUN PER ZIP (isolated)
###############################################################################

require_file "$PHOTO_SCRIPTS/scripts/run_pipeline_core.sh"

for zip_path in "${zips[@]}"; do
  zip_base="$(basename "$zip_path")"
  zip_stem="${zip_base%.*}"
  zip_stem="${zip_stem// /_}"
  ts="$(date +%Y-%m-%d_%H_%M_%S)"

  run_label="${ts}__${zip_stem}"
  run_dir="$RUNS_ROOT/$run_label"
  suffix=2
  while [[ -e "$run_dir" ]]; do
    run_label="${ts}__${zip_stem}__${suffix}"
    run_dir="$RUNS_ROOT/$run_label"
    suffix=$((suffix + 1))
  done

  export RUN_LABEL="$run_label"
  export RUN_DIR="$run_dir"
  export RUN_LOG="$RUN_DIR/run.log"
  export TAKEOUT_UNZIPPED_ROOT="$RUN_DIR/unzipped"

  if [[ -z "$USER_TAKEOUT_BATCH_ID" ]]; then
    export TAKEOUT_BATCH_ID="$RUN_LABEL"
  else
    export TAKEOUT_BATCH_ID="$USER_TAKEOUT_BATCH_ID"
  fi

  mkdir -p "$RUN_DIR"
  mkdir -p "$TAKEOUT_UNZIPPED_ROOT"

  log "Run label: $RUN_LABEL"
  log "RUN_DIR: $RUN_DIR"
  log "RUN_LOG: $RUN_LOG"
  log "ZIP: $zip_path"
  log "TAKEOUT_UNZIPPED_ROOT: $TAKEOUT_UNZIPPED_ROOT"
  log "PHOTO_ARCHIVE: $PHOTO_ARCHIVE"
  log "PHOTO_SCRIPTS: $PHOTO_SCRIPTS"
  log "ACCOUNTS_STR: $ACCOUNTS_STR"
  log "PREFERRED_ACCOUNT: $PREFERRED_ACCOUNT"
  log "CANON: $CANON"
  log "TAKEOUT_BATCH_ID: $TAKEOUT_BATCH_ID"
  log "INGEST_TOOL: $INGEST_TOOL"

  log "Unzipping ZIP into run-scoped dir"
  unzip -oq "$zip_path" -d "$TAKEOUT_UNZIPPED_ROOT"

  log "Running pipeline core: $PHOTO_SCRIPTS/scripts/run_pipeline_core.sh"
  bash "$PHOTO_SCRIPTS/scripts/run_pipeline_core.sh" | tee -a "$RUN_LOG"

  log "Backing up CANON to: $CANON_BACKUP_DEST"
  mkdir -p "$CANON_BACKUP_DEST"
  rsync -aAXHv --info=progress2 --itemize-changes \
    --exclude="._*" --exclude=".DS_Store" \
    "$PHOTO_ARCHIVE/CANONICAL/" \
    "$CANON_BACKUP_DEST/" \
    | tee -a "$RUN_LOG"

  log "RUN DONE."
  log "Log: $RUN_LOG"
done

log "ALL DONE."
