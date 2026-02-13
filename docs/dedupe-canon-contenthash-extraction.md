# Dedupe Canonical ContentHash Extraction

**Answer:** YES — contentHash can be derived from the canonical path without reading bytes.

**Canonical Layout Observed (Dedupe Pipeline)**
- Canonical directory is configured via `CANON` (e.g., `PHOTO_ARCHIVE/CANONICAL/by-hash`).
- Canonical media files are stored directly under the `by-hash` directory with no sharding.
- Filename pattern is `<64-hex-sha256><ext>` (e.g., `.../by-hash/<sha256>.jpg`).

**Extraction Rule**
- Input: absolute canonical path, e.g. `/Volumes/ShMedia/PHOTO_ARCHIVE/CANONICAL/by-hash/<sha256>.<ext>`.
- Output: `contentHash` = the 64-hex SHA-256 from the filename (excluding the extension).
- Hash type: SHA-256.
- Filename format: `<sha256><ext>` where `sha256` is 64 hex characters; `ext` starts with a dot.
- Normalization: lowercase hex for the returned hash.
- Validation: filename must match regex `^[0-9a-fA-F]{64}\.[^./\\]+$` (case-insensitive hex, single extension).
- Error handling: if the filename does not match, return `null` (or skip with warning).

Optional TypeScript helper (illustrative only):
```ts
export function contentHashFromCanonPath(p: string): string | null {
  const base = p.split(/[\\/]/).pop() ?? "";
  const m = /^([0-9a-f]{64})\.[^./\\]+$/i.exec(base);
  if (!m) return null;
  return m[1].toLowerCase();
}
```

**Examples**
- `/Volumes/ShMedia/PHOTO_ARCHIVE/CANONICAL/by-hash/0004361fb4fb6926b119c1415aebd300b0134d00a3efdadb52eca1d21bcf2234.jpg` → `0004361fb4fb6926b119c1415aebd300b0134d00a3efdadb52eca1d21bcf2234`
- `/Volumes/ShMedia/PHOTO_ARCHIVE/CANONICAL/by-hash/0018cb135522545ad7080ba10163820d089445077439897e18245f59ac65dc1d.jpg` → `0018cb135522545ad7080ba10163820d089445077439897e18245f59ac65dc1d`
- `/Volumes/ShMedia/PHOTO_ARCHIVE/CANONICAL/by-hash/0027e1f89581c596d2ea38905b9f565d57e5d07b2d91401ec762dff032f222bb.jpg` → `0027e1f89581c596d2ea38905b9f565d57e5d07b2d91401ec762dff032f222bb`
- `/Volumes/ShMedia/PHOTO_ARCHIVE/CANONICAL/by-hash/0030892d2c4d486168072676f0431cc82de9c626aacd607943329d4f26531e0a.jpg` → `0030892d2c4d486168072676f0431cc82de9c626aacd607943329d4f26531e0a`
- `/Volumes/ShMedia/PHOTO_ARCHIVE/CANONICAL/by-hash/003773a045e3f93847ed600cf4c62164052fae84f0e198074b93e04849f4f098.jpg` → `003773a045e3f93847ed600cf4c62164052fae84f0e198074b93e04849f4f098`

**Where This Comes From (Code References)**
- `scripts/run_everything.sh` (sets `CANON="$PHOTO_ARCHIVE/CANONICAL/by-hash"`).
- `scripts/materialize_canonicals.py` (writes canonical files to `os.path.join(CANON, f"{sha}{ext}")`).
- `scripts/build_run_plan.py` (hash algorithm is SHA-256; canonical filename regex `<64-hex-sha256><ext>`).
- `scripts/canonical_inventory.py` (validates canonical filenames with the same `<sha256><ext>` regex and records `sha256` field).
- `scripts/write_sidecars_from_takeout.py` (canonical media path is `os.path.join(CANON, f"{sha}{ext}")`).

**Notes / Caveats**
- This applies to the dedupe pipeline’s canonical output only (not the Shafferography app layout).
- The canonical layout is a flat directory (no sharding). If a future layout adds sharding, the extraction rule would need to parse the filename or additional path segments accordingly.
