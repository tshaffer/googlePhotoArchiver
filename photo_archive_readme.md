# PHOTO_ARCHIVE – Canonical Google Photos Deduplication & Archival Workflow

This document describes the **end‑to‑end workflow** for building and maintaining a long‑term, deduplicated photo archive using Google Photos Takeout, with **SHA‑256 content‑addressed canonicals** and regenerable human‑friendly views.

Design goals:

- A **single, immutable canonical archive** for all photos you intend to keep long‑term
- **Deterministic deduplication** across multiple Google accounts and Takeout runs
- Clear separation between **truth (canonicals)** and **views (organization)**
- A workflow that is **repeatable, auditable, and safe to re‑run**
- Support **multiple Takeout ZIPs per account per run** (chunked exports are normal)

This archive is intended to be the long‑term source for applications such as **Shafferography**, backups, and future tooling.

---

## Important: Google Takeout archive hygiene

Before starting any new run, the Takeout input directory **must contain only new, unprocessed Google Takeout archives**.

All Takeout ZIP files that were successfully processed in a prior run **must be removed or moved out of the input directory** before starting a new run.

The current pipeline treats all Takeout archives present at run start as authoritative inputs for that run. Leaving previously processed Takeout archives in place will cause files to be re-enumerated and may result in:

- Reprocessing of already-ingested photos
- Duplicate or rewritten sidecar metadata
- Incorrect inventories or manifests
- Confusing or misleading deduplication results

This cleanup step is **required** and is not optional in the current design.

---

## High‑level architecture

- **CANONICAL/** – immutable truth (content‑addressed by SHA‑256)
- **GOOGLE_TAKEOUT/** – raw inputs (never trusted long‑term)
- **MANIFESTS/** – provenance, dedup decisions, and audit artifacts
- **VIEWS/** – regenerable, human‑friendly directory trees (symlinks only)

Only **CANONICAL/** and **MANIFESTS/** must be backed up rigorously.

---

## Directory layout

This section describes **every directory that may appear under `PHOTO_ARCHIVE/`**, its purpose, and whether it is authoritative, transient, or deprecated.

```text
PHOTO_ARCHIVE/
├── CANONICAL/
│   ├── by-hash/                         # Immutable canonical media files
│   │   ├── <sha256>.<ext>
│   │   └── <sha256>.<ext>.shafferography.json   # Optional per-canonical sidecar
│   └── README_CANONICAL.md              # Canonical invariants and rules
│
├── GOOGLE_TAKEOUT/
│   ├── <account>/
│   │   ├── zips/                        # Original Takeout ZIPs (never modified)
│   │   └── unzipped/                    # Expanded Takeout contents (read-only)
│   │       └── <zip-stem>/Takeout/Google Photos/...
│   └── (additional accounts)
│
├── MANIFESTS/
│   ├── latest/                          # Convenience copies/symlinks to latest run outputs (optional)
│   └── runs/
│       └── <RUN_LABEL>/                 # Per-run outputs (authoritative, append-only)
│           ├── dedup_plan__unique.csv
│           ├── dedup_plan__duplicates.csv
│           ├── canonical_inventory__by-hash.csv
│           └── (future audit / provenance manifests)
│
├── VIEWS/
│   ├── by-date/                         # EXIF-derived date view (symlinks only)
│   │   └── NO_EXIF/                     # Files lacking usable EXIF dates
│   └── by-date-takeout/                 # Date view derived from Takeout JSON
│
├── DEDUP_WORK/                          # Ephemeral scratch space for scripts
├── DEDUP_RESULTS/                       # Deprecated transitional outputs (do not use)
├── INBOX/                               # Human-facing intake buffer (pre-canonical)
├── LOGS/                                # Execution logs (non-authoritative)
│
└── scripts/                             # (Optional) helper shell scripts local to the archive
```

### Directory responsibilities

- **CANONICAL/** (authoritative, immutable)  
  - The single source of truth  
  - Must be backed up  
  - Never edited in place

- **GOOGLE_TAKEOUT/** (inputs/provenance)  
  - Raw inputs and provenance  
  - Can be re-downloaded if lost (slow but possible)  
  - Never trusted as long-term storage

- **MANIFESTS/** (authoritative audit trail)  
  - The “memory” of the pipeline  
  - Records decisions, provenance, and audit state  
  - Small, critical, must be backed up  
  - Stored **per run** under `MANIFESTS/runs/<RUN_LABEL>/` so runs never collide

- **VIEWS/** (non-authoritative, regenerable)  
  - Human-friendly organization layers  
  - Symlinks only  
  - Fully regenerable

- **DEDUP_WORK/** (transient)  
  - Temporary working area for hashing, planning, and experimentation  
  - Safe to delete at any time  
  - Never backed up

- **DEDUP_RESULTS/** (deprecated)  
  - Legacy/transitional directory from earlier workflow iterations  
  - Superseded by `CANONICAL/` + `MANIFESTS/`  
  - Safe to remove once all legacy scripts are retired

- **INBOX/** (transient intake)  
  - Pre-archive intake buffer (e.g., AirDrop, camera imports)  
  - Files are provisional and may be deleted or promoted  
  - Not part of the long-term archive

- **LOGS/** (diagnostic only)  
  - Script and rsync execution logs  
  - Useful for troubleshooting only  
  - Not authoritative; optional to retain

---

## Core concepts

### Canonical identity
- Every photo/video is identified **only** by its SHA‑256 hash
- Canonical filename format: `<sha256><ext>`
- The same bytes **must never appear twice** in `CANONICAL/by-hash`

### Immutability rule
Files under `CANONICAL/by-hash`:
- must never be renamed
- must never be edited in place (including EXIF)
- must never be deleted except via an explicit, audited decision

All organization happens via **symlinks in `VIEWS/`**.

---

## One‑time setup (done once per archive)

These steps establish **structural invariants**, not policy decisions that may evolve.

1. Create `PHOTO_ARCHIVE` root on primary storage
2. Establish canonical layout (`CANONICAL/by-hash` as the immutable store)
3. Define dedup mechanics (hash algorithm, byte-for-byte equality, extension handling)
4. Create backup target(s) for `CANONICAL/`
5. Write canonical README and invariants

### About account precedence (important)

Account precedence (e.g., “which account wins when identical bytes appear in multiple accounts”) is **not** a one-time decision.

- It is a **policy input to each dedup run**
- Different runs may use different precedence rules
- New Google accounts may be introduced later

Each run records its decision inputs in the per-run manifests.

---

## Takeout ingestion workflow

This applies both to your **first historical ingest** and to **recurring** new Takeout downloads.

### Step 1 — Download Takeouts (multiple ZIPs are normal)
For each Google Photos account:
- Download one or more Takeout ZIPs (album-scoped and/or chunked)
- Preserve ZIP filenames (provenance)

### Step 2 — Stage raw Takeouts
- Copy ZIPs into `GOOGLE_TAKEOUT/<account>/zips/`
- Unzip each ZIP into `GOOGLE_TAKEOUT/<account>/unzipped/<zip-stem>/`

**Never modify files inside `GOOGLE_TAKEOUT/`.**

### Step 3 — Hash & deduplicate
- Walk all staged media files across **all accounts** and **all unzipped ZIP folders**
- Compute SHA‑256 hashes
- Build a dedup plan:
  - `dedup_plan__unique.csv`
  - `dedup_plan__duplicates.csv`
- Apply account precedence rules for ties

### Step 4 — Materialize canonicals
- For each unique SHA:
  - Copy exactly one file into `CANONICAL/by-hash/<sha>.<ext>`
- If a SHA already exists in `CANONICAL/by-hash`, it is treated as already ingested and **not copied again**
- No rename, no metadata edits

### Step 5 — Create inventory (audit)
- Generate `canonical_inventory__by-hash.csv` as an integrity baseline (tripwire)

### Step 6 — Persist optional per-canonical sidecars (recommended)
- Write `CANONICAL/by-hash/<sha><ext>.shafferography.json`
- Sidecars preserve Google-only fields (see **Persisted Google Takeout sidecar metadata (v1)** below)

### Step 7 — Build views (optional)
- `VIEWS/by-date/` from EXIF (with `NO_EXIF` bucket)
- `VIEWS/by-date-takeout/` from Takeout supplemental JSON

Views are **always optional** and **always regenerable**.

---

## Recurring workflow (each new Takeout download)

Whenever you download **new** Google Photos Takeouts:

1. Add ZIPs to `GOOGLE_TAKEOUT/<account>/zips/`
2. Unzip into `GOOGLE_TAKEOUT/<account>/unzipped/<zip-stem>/`
3. Re-run hash + dedup planning (against **existing** canonicals)
4. Apply plan:
   - Existing SHA → recorded as duplicate, not materialized
   - New SHA → copied into `CANONICAL/by-hash`
5. Write per-run manifests under `MANIFESTS/runs/<RUN_LABEL>/`
6. Regenerate views (optional)
7. Back up `CANONICAL/` and `MANIFESTS/`

### What “previously imported photos are skipped automatically” means

All staged media files are still discovered and hashed.

“Skipped” refers to the **materialization step**:
- Existing hashes cause no new files to be written
- Duplicate instances are recorded in `dedup_plan__duplicates.csv`

Because identity is content-addressed, this behavior is deterministic and independent of filenames, dates, or accounts.

---

## Backup strategy (summary)

### Must back up
- `CANONICAL/`
- `MANIFESTS/`

### Optional
- `VIEWS/` (regenerable)
- `GOOGLE_TAKEOUT/` (can be re-downloaded)

Use `rsync` to mirror `CANONICAL/` to at least one external drive.

---

## Relationship to Shafferography

- Shafferography imports only from `CANONICAL/by-hash`
- Photo ID = SHA‑256
- No bytes are copied into the DB
- EXIF and provenance are imported as metadata

Shafferography is a **catalog and review system**, not a storage system.

---

## Known limitations (by design)

- No deterministic link back to Google Photos UI (unless you later add a Photos API ingest step)
- Capture dates may be missing from EXIF
- Takeout JSON coverage is incomplete / inconsistent

These are Google Photos constraints, not archive flaws.

---

## Philosophy (why this works long‑term)

- Content‑addressed storage scales indefinitely
- Views are cheap and disposable
- Provenance lives in manifests/sidecars, not filenames
- Backups are boring and reliable

If in doubt: **never touch `CANONICAL` directly**.

---

## Persisted Google Takeout sidecar metadata (v1)

In addition to immutable canonicals, each canonical media file may have a colocated sidecar:

```text
CANONICAL/by-hash/<sha256><ext>.shafferography.json
```

This sidecar preserves Google-only fields through dedupe and is available to Shafferography at import time.

### Persisted fields (v1)
- `source.googlePhotoIds[]` (array)
- `provenance` (takeout batch + ingest timestamp + tool)
- `original` (filename + Takeout path + optional metadata path)
- `googleTakeout.people[]`
- `googleTakeout.geoData`

### Merge policy
- These fields are stored **outside EXIF**.
- If GPS already exists in EXIF, the decision to prefer EXIF vs Google `geoData` is deferred to Shafferography import.

---

End of document.
