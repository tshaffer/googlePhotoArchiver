#!/usr/bin/env bash
set -euo pipefail

: "${PHOTO_ARCHIVE:?required}"
: "${PHOTO_SCRIPTS:?required}"
: "${CANON:?required}"
: "${RUN_LOG:?required}"

# Needed by build_run_plan.py
: "${ACCOUNTS_STR:?required}"
: "${PREFERRED_ACCOUNT:?required}"

# Strongly recommended so manifests are per-run and never collide
: "${RUN_LABEL:?required}"

# Ensure python can import lib.env without relying on caller
export PYTHONPATH="${PYTHONPATH:-$PHOTO_SCRIPTS}"

check_canon_tripwire() {
  if find "$CANON" -type f -name '._*' -print -quit | grep -q .; then
    echo "ERROR: AppleDouble files (._*) present in CANON: $CANON" >&2
    exit 1
  fi

  if find "$CANON" -type f -name '.DS_Store' -print -quit | grep -q .; then
    echo "ERROR: .DS_Store present in CANON: $CANON" >&2
    exit 1
  fi
}

# Clean macOS junk from canonicals (safe)
find "$CANON" -type f -name '._*' -delete || true
find "$CANON" -type f -name '.DS_Store' -delete || true

# Tripwire after cleanup
check_canon_tripwire
python3 "$PHOTO_SCRIPTS/scripts/check_canon_clean.py" | tee -a "$RUN_LOG"

python3 "$PHOTO_SCRIPTS/scripts/build_run_plan.py"              | tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/materialize_canonicals.py"      | tee -a "$RUN_LOG"
check_canon_tripwire
python3 "$PHOTO_SCRIPTS/scripts/write_sidecars_from_takeout.py" | tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/canonical_inventory.py"         | tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/build_view_by_date_exif.py"     | tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/build_view_by_date_takeout.py"  | tee -a "$RUN_LOG"

# Tripwire at pipeline end
check_canon_tripwire
python3 "$PHOTO_SCRIPTS/scripts/check_canon_clean.py" | tee -a "$RUN_LOG"
