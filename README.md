# PHOTO_SCRIPTS

This repository contains the reproducible, script-based pipeline used to deduplicate Google Photos Takeout exports and materialize a canonical photo archive with preserved provenance and metadata.

Scripts are driven by environment variables and are intended to be run either individually or via a small shell wrapper.

---

## Required environment variables

These **must** be set before running any scripts:

- `PHOTO_ARCHIVE`  
  Root directory for all photo-archive data  
  Example: `/Volumes/ShMedia/PHOTO_ARCHIVE`

- `PHOTO_SCRIPTS`  
  Absolute path to this repository  
  Example: `/Users/tedshaffer/Documents/Projects/photo-scripts`

- `CANON`  
  Directory where canonical media files are stored  
  Example: `$PHOTO_ARCHIVE/CANONICAL/by-hash`

- `ACCOUNTS_STR`  
  Whitespace-delimited list of Google account identifiers.  
  These must match directory names under `PHOTO_ARCHIVE/GOOGLE_TAKEOUT/`.  
  Example: `ACCOUNTS_STR="shafferFamily shafferFamilyPhotosTLSJR"`

- `PREFERRED_ACCOUNT`  
  Account whose copy should be preferred when duplicates exist (policy for this run).  
  Example: `PREFERRED_ACCOUNT="shafferFamilyPhotosTLSJR"`

- `RUN_LABEL`  
  Identifier for this pipeline run. Used to isolate manifests and logs.  
  Example: `RUN_LABEL="2026-02-05_21_30__takeout_ingest"`

---

## Optional environment variables (recommended)

These have safe defaults but are recommended for traceability:

- `TAKEOUT_BATCH_ID`  
  Defaults to `RUN_LABEL`  
  Used in sidecar provenance

- `INGEST_TOOL`  
  Defaults to `dedupe-pipeline`

- `RUN_LOG`  
  Path to a log file if you are tee’ing script output

---

## Python import setup (required)

All scripts expect this repo to be importable (e.g., for `lib/`).

Before running **any** Python script:

```bash
export PYTHONPATH="$PHOTO_SCRIPTS"
```

---

## Expected archive structure

Scripts assume the following (created by the runbook):

- Takeouts staged under:  
  `PHOTO_ARCHIVE/GOOGLE_TAKEOUT/<account>/{zips,unzipped}`

- Canonicals written to:  
  `PHOTO_ARCHIVE/CANONICAL/by-hash`

- Manifests written **per run** to:  
  `PHOTO_ARCHIVE/MANIFESTS/runs/<RUN_LABEL>/`

Optional convenience pointers may be updated under:
- `PHOTO_ARCHIVE/MANIFESTS/latest/`

---

## Script responsibilities

(Names reflect your current pipeline wrapper.)

- `scripts/build_run_plan.py`  
  - Scans all staged takeouts for all accounts
  - Hashes all media files
  - Applies `PREFERRED_ACCOUNT` when the same SHA appears multiple places
  - Writes per-run manifests:
    - `dedup_plan__unique.csv`
    - `dedup_plan__duplicates.csv`

- `scripts/materialize_canonicals.py`  
  - Reads the run plan’s `dedup_plan__unique.csv`
  - Copies bytes into `CANON/` only for SHAs not already present
  - Must **never** mutate existing canonicals

- `scripts/write_sidecars_from_takeout.py`  
  - Reads the manifests and Takeout JSON sidecars
  - Writes one sidecar per canonical:
    - `<sha><ext>.shafferography.json`
  - Populates provenance fields using `TAKEOUT_BATCH_ID` + `INGEST_TOOL`

- `scripts/canonical_inventory.py`  
  - Writes `canonical_inventory__by-hash.csv` for the current canonical directory
  - Serves as an integrity tripwire

---

## Standard pipeline invocation

From your shell wrapper:

```bash
set -euo pipefail

: "${PHOTO_ARCHIVE:?required}"
: "${PHOTO_SCRIPTS:?required}"
: "${CANON:?required}"
: "${RUN_LOG:?required}"
: "${ACCOUNTS_STR:?required}"
: "${PREFERRED_ACCOUNT:?required}"
: "${RUN_LABEL:?required}"

export PYTHONPATH="$PHOTO_SCRIPTS"

python3 "$PHOTO_SCRIPTS/scripts/build_run_plan.py"              | tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/materialize_canonicals.py"      | tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/write_sidecars_from_takeout.py" | tee -a "$RUN_LOG"
python3 "$PHOTO_SCRIPTS/scripts/canonical_inventory.py"         | tee -a "$RUN_LOG"
```

---

## Notes and invariants

- Scripts must treat **multiple Takeout ZIPs per account** as normal:
  - zip folder: `GOOGLE_TAKEOUT/<account>/zips/*.zip`
  - unzip folder: `GOOGLE_TAKEOUT/<account>/unzipped/<zip-stem>/...`
- Scripts must never assume a single takeout root folder.
- All writes to MANIFESTS should be run-isolated under `MANIFESTS/runs/<RUN_LABEL>/`.
- Canonical directory must not contain AppleDouble `._*` files or `.DS_Store`; pipeline cleanup removes them and tripwires fail if they reappear.

---

End of document.
