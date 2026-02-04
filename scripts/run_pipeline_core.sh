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

# Optional but useful: defaults live in the python scripts if you omit these
# : "${TAKEOUT_BATCH_ID:?optional}"
# : "${INGEST_TOOL:?optional}"

python3 "$PHOTO_SCRIPTS/scripts/build_run_plan.py"              | tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/materialize_canonicals.py"      | tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/write_sidecars_from_takeout.py" | tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/canonical_inventory.py"         | tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/build_view_by_date_exif.py"     | tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/build_view_by_date_takeout.py"  | tee -a "$RUN_LOG"
