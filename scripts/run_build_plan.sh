#!/usr/bin/env bash
set -euo pipefail

export PHOTO_SCRIPTS="/Users/tedshaffer/Documents/Projects/googlePhotoArchiver"
export PYTHONPATH="$PHOTO_SCRIPTS"
export PHOTO_ARCHIVE="/Volumes/ShMedia/PHOTO_ARCHIVE"
export PREFERRED_ACCOUNT="shafferFamilyPhotosTLSJR"
export CANON="$PHOTO_ARCHIVE/CANONICAL/by-hash"
export RUN_LABEL="$(date +%Y-%m-%d_%H_%M)__takeout_ingest"
export ACCOUNTS_STR="shafferFamily shafferFamilyPhotosTLSJR"

bash "$PHOTO_SCRIPTS/scripts/run_pipeline_core.sh"
