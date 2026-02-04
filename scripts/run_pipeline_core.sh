#!/usr/bin/env bash
set -euo pipefail

: "${PHOTO_SCRIPTS:?required}"
: "${CANON:?required}"
: "${RUN_LOG:?required}"

python3 "$PHOTO_SCRIPTS/scripts/build_run_plan.py"            | tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/materialize_canonicals.py"    | tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/write_sidecars_from_takeout.py"| tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/canonical_inventory.py"       | tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/build_view_by_date_exif.py"       | tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/build_view_by_date_takeout.py"       | tee -a "$RUN_LOG"
