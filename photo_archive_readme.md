# PHOTO_ARCHIVE – Canonical Google Photos Deduplication & Archival Workflow

This document describes the **end‑to‑end workflow** for building and maintaining a long‑term, deduplicated photo archive using Google Photos Takeout, with **SHA‑256 content‑addressed canonicals** and regenerable human‑friendly views.

The design goals are:
- A **single, immutable canonical archive** for all photos you intend to keep long‑term
- **Deterministic deduplication** across multiple Google accounts and Takeout runs
- Clear separation between **truth (canonicals)** and **views (organization)**
- A workflow that is **repeatable, auditable, and safe to re‑run**

This archive is intended to be the long‑term source for applications such as **Shafferography**, backups, and future tooling.

---

## High‑level architecture

- **CANONICAL/** – the immutable truth (content‑addressed by SHA‑256)
- **GOOGLE_TAKEOUT/** – raw inputs (never trusted long‑term)
- **MANIFESTS/** – provenance, dedup decisions, and audit artifacts
- **VIEWS/** – regenerable, human‑friendly directory trees (symlinks only)

Only **CANONICAL/** must be backed up rigorously.

---

## Directory layout

This section describes **every directory that may appear under `PHOTO_ARCHIVE/`**, its purpose, and whether it is authoritative, transient, or deprecated.

```
PHOTO_ARCHIVE/
├── CANONICAL/
│   ├── by-hash/                  # Immutable canonical media files
│   │   └── <sha256>.<ext>
│   └── README_CANONICAL.md        # Canonical invariants and rules
│
├── GOOGLE_TAKEOUT/
│   ├── <account>/
│   │   ├── zips/                  # Original Google Takeout ZIPs (never modified)
│   │   └── unzipped/              # Expanded Takeout contents (read-only)
│   │       └── Takeout/Google Photos/...
│   └── (additional accounts)
│
├── MANIFESTS/
│   ├── dedup_plan__unique.csv     # One row per canonical SHA chosen
│   ├── dedup_plan__duplicates.csv # All non-canonical duplicates
│   ├── canonical_inventory__by-hash.csv
│   └── (future audit / provenance manifests)
│
├── VIEWS/
│   ├── by-date/                  # EXIF-derived date view (symlinks only)
│   │   └── NO_EXIF/               # Files lacking usable EXIF dates
│   └── by-date-takeout/           # Date view derived from Takeout JSON
│
├── DEDUP_WORK/                   # Ephemeral scratch space for dedup scripts
├── DEDUP_RESULTS/                # Deprecated transitional outputs (do not use)
├── INBOX/                        # Human-facing intake buffer (pre-canonical)
├── LOGS/                         # Execution logs (non-authoritative)
│
└── (future directories)
```

### Directory responsibilities

- **CANONICAL/**  
  - The single source of truth  
  - Must be backed up  
  - Never edited in place

- **GOOGLE_TAKEOUT/**  
  - Raw inputs and provenance  
  - Can be re-downloaded if lost  
  - Never trusted as long-term storage

- **MANIFESTS/**  
  - The “memory” of the pipeline  
  - Records decisions, provenance, and audit state  
  - Small, critical, and must be backed up

- **VIEWS/**  
  - Human-friendly organization layers  
  - Symlinks only  
  - Fully regenerable

- **DEDUP_WORK/**  
  - Temporary working area for hashing, planning, and experimentation  
  - Safe to delete at any time  
  - Never backed up

- **DEDUP_RESULTS/**  
  - Legacy / transitional directory from earlier workflow iterations  
  - Superseded by `CANONICAL/`  
  - Should not be used for new work; safe to remove once legacy scripts are retired

- **INBOX/**  
  - Pre-archive intake buffer (e.g., AirDrop, camera imports)  
  - Files are provisional and may be deleted or promoted  
  - Not part of the long-term archive

- **LOGS/**  
  - Script and rsync execution logs  
  - Useful for troubleshooting only  
  - Not authoritative; optional to retain


---

## Core concepts

### Canonical identity
- Every photo/video is identified **only** by its SHA‑256 hash
- Filename format: `<sha256><ext>`
- The same bytes **must never appear twice** in CANONICAL

### Immutability rule
Files under `CANONICAL/by-hash`:
- must never be renamed
- must never be edited in place (including EXIF)
- must never be deleted except via an explicit, audited decision

All organization happens via **symlinks in VIEWS/**.

---

## One‑time setup (done once per archive)

These steps establish **structural invariants**, not policy decisions that may evolve.

1. **Create PHOTO_ARCHIVE root** on primary storage
2. **Establish canonical layout** (`CANONICAL/by-hash` as the immutable store)
3. **Define dedup mechanics** (hash algorithm, byte-for-byte equality, extension handling)
4. **Create backup target(s)** for CANONICAL
5. **Write canonical README and invariants**

### About account precedence (important)

Account precedence (e.g. “which account wins when identical bytes appear in multiple accounts”) is **not a one-time decision**.

- It is a **policy input to each dedup run**
- Different runs may use different precedence rules
- New Google accounts may be introduced in the future

The outcome of each run is recorded in manifests, but the archive design does **not** assume a single forever-primary account.


---

## First‑time Takeout ingestion workflow

This applies the **first time** you ingest historical Google Photos Takeouts.

### Step 1 — Download Takeouts
For each Google Photos account:
- Download one or more Takeout ZIPs (album‑scoped or chunked)
- Preserve ZIP filenames (they are provenance)

### Step 2 — Stage raw Takeouts
- Copy ZIPs into:
  - `GOOGLE_TAKEOUT/<account>/zips/`
- Unzip into:
  - `GOOGLE_TAKEOUT/<account>/unzipped/`

**Never modify files inside Takeout directories.**

### Step 3 — Hash & deduplicate
- Walk all staged media files
- Compute SHA‑256 hashes
- Build a dedup plan:
  - `dedup_plan__unique.csv`
  - `dedup_plan__duplicates.csv`
- Apply account precedence rules

### Step 4 — Materialize canonicals
- For each unique SHA:
  - Copy exactly one file into `CANONICAL/by-hash/<sha>.<ext>`
- Do not rename or edit files

### Step 5 — Create inventory (audit)
- Generate `canonical_inventory__by-hash.csv`
- This is your integrity baseline

### Step 6 — Build views (optional but recommended)
- `VIEWS/by-date/` from EXIF (with NO_EXIF bucket)
- `VIEWS/by-date-takeout/` from `.supplemental-metadata.json`

Views are **always optional** and **always regenerable**.

---

## Recurring workflow (each new Takeout download)

Whenever you download **new** Google Photos Takeouts:

1. Add ZIPs to:
   - `GOOGLE_TAKEOUT/<account>/zips/`
2. Unzip into:
   - `GOOGLE_TAKEOUT/<account>/unzipped/`
3. Re-run **hash & dedup planning** against *existing canonicals*
4. **Apply dedup plan**:
   - If a file’s SHA-256 already exists in `CANONICAL/by-hash`, it is treated as a duplicate and **not copied**
   - If a SHA-256 is new, it is materialized into `CANONICAL/by-hash`
5. Update manifests
6. Regenerate views (optional)
7. Run canonical backup

### What “previously imported photos are skipped automatically” means

All staged media files are still discovered and hashed.

“Skipped” refers specifically to the **materialization step**:
- Existing hashes cause no new files to be written
- Duplicate instances are recorded in `dedup_plan__duplicates.csv`

Because identity is content-addressed, this behavior is deterministic and independent of filenames, dates, or accounts.


---

## Backup strategy (summary)

Back up **only** what matters:

### Must back up
- `CANONICAL/`
- `MANIFESTS/`

### Optional
- `VIEWS/` (regenerable)
- `GOOGLE_TAKEOUT/` (can be re-downloaded)

Use `rsync` to mirror CANONICAL to at least one external drive.

---

## Relationship to Shafferography

- Shafferography **imports only from `CANONICAL/by-hash`**
- Photo ID = SHA‑256
- No bytes are copied into the DB
- EXIF and provenance are imported as metadata

Shafferography is a **catalog and review system**, not a storage system.

---

## Known limitations (by design)

- No deterministic link back to Google Photos UI
- Capture dates may be missing from EXIF
- Google Takeout JSON coverage is incomplete

These are Google Photos constraints, not archive flaws.

---

## Philosophy (why this works long‑term)

- Content‑addressed storage scales indefinitely
- Views are cheap and disposable
- Provenance lives in manifests, not filenames
- Backups are boring and reliable

If in doubt: **never touch CANONICAL directly**.

---

## Future extensions (intentionally deferred)

- Shafferography import
- Google Photos API ingest (with mediaItem IDs)
- Additional views (by‑event, by‑album, by‑people)
- Automated integrity checks

---

End of document.

---

## Persisted Google Takeout sidecar metadata (v1)

In addition to immutable canonicals, each canonical media file may have a colocated sidecar:

```
CANONICAL/by-hash/<sha256><ext>.shafferography.json
```

This sidecar preserves Google-only fields through dedupe and is available to Shafferography at import time.

### Persisted fields
- `source.googlePhotoIds[]` (array)
- `provenance` (takeout batch + ingest timestamp + tool)
- `original` (filename + Takeout paths)
- `googleTakeout.people[]`
- `googleTakeout.geoData`

### Merge policy
- These fields are stored **outside EXIF**.
- If GPS already exists in EXIF, the decision to prefer EXIF vs Google `geoData` is deferred to Shafferography import.

