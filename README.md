# PHOTO_SCRIPTS

This repository contains the reproducible, script-based pipeline used to
deduplicate Google Photos Takeout exports and materialize a canonical photo
archive with preserved provenance and metadata.

All scripts are **purely driven by environment variables** and are intended
to be run either individually or via the provided pipeline shell script.

---

## Required environment variables

These **must** be set before running any scripts:

- `PHOTO_ARCHIVE`  
  Root directory for all photo-archive data  
  (e.g. `/Volumes/ShMedia/PHOTO_ARCHIVE`)

- `PHOTO_SCRIPTS`  
  Path to this repository

- `CANON`  
  Directory where canonical media files are stored  
  (e.g. `$PHOTO_ARCHIVE/CANONICAL/by-hash`)

- `ACCOUNTS_STR`  
  Whitespace-delimited list of Google account identifiers  
  (must match directory names under `GOOGLE_TAKEOUT/`)  
  Example:

- `PREFERRED_ACCOUNT`  
Account whose copy should be preferred when duplicates exist

- `RUN_LABEL`  
Identifier for this pipeline run.  
Used to isolate manifests and logs.
Example:

---

## Optional environment variables

These have safe defaults but are recommended for traceability:

- `TAKEOUT_BATCH_ID`  
Defaults to `RUN_LABEL`  
Used in sidecar provenance

- `INGEST_TOOL`  
Defaults to `dedupe-pipeline`

- `RUN_LOG`  
Path to a log file when running the pipeline shell script

---

## Python import setup (required)

All scripts expect `lib/` to be importable.

Before running **any** Python script:

```bash
export PYTHONPATH="$PHOTO_SCRIPTS"
