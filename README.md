# PHOTO_SCRIPTS

These scripts expect you to set:

- `PHOTO_ARCHIVE`
- `CANON`
- `ACCOUNTS_STR`
- `PREFERRED_ACCOUNT`
- (optional) `RUN_LABEL`, `TAKEOUT_BATCH_ID`, `INGEST_TOOL`

**Important:** run with:

    export PYTHONPATH="$PHOTO_SCRIPTS"

so `from lib.env import ...` works.

Example:

    export PHOTO_SCRIPTS="/path/to/photo_scripts_repo"
    export PYTHONPATH="$PHOTO_SCRIPTS"
    python3 "$PHOTO_SCRIPTS/scripts/build_run_plan.py"
