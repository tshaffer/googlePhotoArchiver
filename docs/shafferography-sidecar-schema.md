# Shafferography Sidecar Schema — 2026-02-06

## Overview
Per-canonical sidecars are written to `PHOTO_ARCHIVE/CANONICAL/by-hash/*.shafferography.json` by the dedupe pipeline. The schema below is derived from the writer in `scripts/write_sidecars_from_takeout.py` and verified against a real output file.

## Full JSON Schema

| JSON path | Type | Required? | Source / derivation |
|---|---|---|---|
| `version` | number | always | Constant `1` in writer (`sidecar` dict). |
| `source` | object | always | Constructed in writer. |
| `source.system` | string | always | Constant `"google-photos-takeout"`. |
| `source.googlePhotoIds` | array of string | always (may be empty) | From Takeout sidecar fields via `extract_google_photo_ids`: `url` (regex `/photo/<id>`), `photoId`, `mediaId`, `googlePhotoId`, `id` (recursive search). |
| `source.googlePhotoId` | string | always (may be empty) | First ID from `source.googlePhotoIds` or empty string. |
| `provenance` | object | always | Constructed in writer. |
| `provenance.takeoutBatchId` | string | always | `TAKEOUT_BATCH_ID` env (defaults to `RUN_LABEL`). |
| `provenance.importedAt` | string (ISO-8601 UTC) | always | `now_utc_iso()` at write time. |
| `provenance.ingestTool` | string | always | `INGEST_TOOL` env (defaults to `"dedupe-pipeline"`). |
| `original` | object | always | Constructed in writer. |
| `original.filename` | string | always | Basename of `absPath` from `dedup_plan__unique.csv`. |
| `original.takeoutPath` | string | always | `GOOGLE_TAKEOUT/<account>/unzipped/<relativePath>` from manifest. |
| `original.metadataPath` | string | always (may be empty) | Relative path to Takeout JSON sidecar if found; empty string if not found. |
| `people` | array of string | always (may be empty) | From Takeout `people[].name`. |
| `geoData` | object or null | always (nullable) | From Takeout `geoData` object; `null` if missing or all values are null. |
| `geoData.latitude` | number or null | present when `geoData` is object | From `geoData.latitude`. |
| `geoData.longitude` | number or null | present when `geoData` is object | From `geoData.longitude`. |
| `geoData.altitude` | number or null | present when `geoData` is object | From `geoData.altitude`. |
| `geoData.latitudeSpan` | number or null | present when `geoData` is object | From `geoData.latitudeSpan`. |
| `geoData.longitudeSpan` | number or null | present when `geoData` is object | From `geoData.longitudeSpan`. |

## Example Sidecar JSON
Example taken from a real output file at:
`/Volumes/ShMedia/PHOTO_ARCHIVE/CANONICAL/by-hash/0a01accaee2d105d3811a3b0852e8e819bc1b6d66b010e4776591b2f85666fad.jpg.shafferography.json`

```json
{
  "version": 1,
  "source": {
    "system": "google-photos-takeout",
    "googlePhotoIds": [],
    "googlePhotoId": ""
  },
  "provenance": {
    "takeoutBatchId": "2026-02-04_11_10__takeout_ingest",
    "importedAt": "2026-02-04T19:11:44Z",
    "ingestTool": "dedupe-pipeline"
  },
  "original": {
    "filename": "AGF00002d39114f5-b3b9-a3f3-b8de-08743142a586.jpg",
    "takeoutPath": "GOOGLE_TAKEOUT/shafferFamilyPhotosTLSJR/unzipped/Takeout/Google Photos/Dedupe 1968 1-13-1969/AGF00002d39114f5-b3b9-a3f3-b8de-08743142a586.jpg",
    "metadataPath": ""
  },
  "people": [],
  "geoData": null
}
```

## Code References
- `scripts/write_sidecars_from_takeout.py`
- `find_takeout_metadata_json` locates per-file Takeout JSON.
- `extract_google_photo_ids` reads `url`, `photoId`, `mediaId`, `googlePhotoId`, `id`.
- `extract_people` reads `people[].name`.
- `extract_geo` reads `geoData.latitude`, `geoData.longitude`, `geoData.altitude`, `geoData.latitudeSpan`, `geoData.longitudeSpan`.
- Sidecar object is built in the main loop and written to `sidecar_path(sha, ext)`.

## Notes / Caveats
- Schema versioning is present via `version: 1`. There is no explicit backward-compatibility logic in the writer.
- `geoData` is `null` when missing or when all extracted geo fields are null.
- `original.metadataPath` is an empty string if no matching Takeout metadata JSON is found.
