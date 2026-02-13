# Takeout Sidecar Fields Usage — 2026-02-06

## Sidecar Fields Parsed

| JSON path | Parsed as | Code location | Notes |
|---|---|---|---|
| `photoTakenTime.timestamp` | integer (seconds) | `scripts/build_view_by_date_takeout.py:parse_google_ts_seconds` | Used if present; preferred over `creationTime.timestamp`. |
| `creationTime.timestamp` | integer (seconds) | `scripts/build_view_by_date_takeout.py:parse_google_ts_seconds` | Fallback if `photoTakenTime.timestamp` is missing. |
| `url` | string | `scripts/write_sidecars_from_takeout.py:extract_google_photo_ids` | Extracts `/photo/<id>` via regex. |
| `photoId` | string (first found) | `scripts/write_sidecars_from_takeout.py:extract_google_photo_ids` + `deep_find_first_string_key` | Searched recursively in JSON. |
| `mediaId` | string (first found) | `scripts/write_sidecars_from_takeout.py:extract_google_photo_ids` + `deep_find_first_string_key` | Searched recursively in JSON. |
| `googlePhotoId` | string (first found) | `scripts/write_sidecars_from_takeout.py:extract_google_photo_ids` + `deep_find_first_string_key` | Searched recursively in JSON. |
| `id` | string (first found) | `scripts/write_sidecars_from_takeout.py:extract_google_photo_ids` + `deep_find_first_string_key` | Searched recursively in JSON. |
| `people[].name` | string | `scripts/write_sidecars_from_takeout.py:extract_people` | Extracts names from `people` array. |
| `geoData.latitude` | number | `scripts/write_sidecars_from_takeout.py:extract_geo` | Extracted if `geoData` object exists. |
| `geoData.longitude` | number | `scripts/write_sidecars_from_takeout.py:extract_geo` | Extracted if `geoData` object exists. |
| `geoData.altitude` | number | `scripts/write_sidecars_from_takeout.py:extract_geo` | Extracted if `geoData` object exists. |
| `geoData.latitudeSpan` | number | `scripts/write_sidecars_from_takeout.py:extract_geo` | Extracted if `geoData` object exists. |
| `geoData.longitudeSpan` | number | `scripts/write_sidecars_from_takeout.py:extract_geo` | Extracted if `geoData` object exists. |

## How Fields Are Used in Dedupe Logic

- Dedupe hashing, grouping, and selection are based on file content hashes computed from media bytes in `scripts/build_run_plan.py` and do not use any sidecar metadata fields.
- Sidecar fields are not used for matching, duplicate detection, grouping, filtering, or tie-breaks in the dedupe pipeline.

## Where Fields Are Persisted

- `PHOTO_ARCHIVE/CANONICAL/by-hash/*.shafferography.json`
- Fields included from sidecar JSON:
- `source.googlePhotoIds` and `source.googlePhotoId` from `url`, `photoId`, `mediaId`, `googlePhotoId`, `id`
- `people` from `people[].name`
- `geoData` from `geoData.*`
- Schema shape:
- `version`, `source`, `provenance`, `original`, `people`, `geoData`
- Writer:
- `scripts/write_sidecars_from_takeout.py` (builds `sidecar` dict and writes JSON).

- `PHOTO_ARCHIVE/VIEWS/by-date-takeout/YYYY/MM/YYYY-MM-DD/<ymd>_<sha10>.<ext>`
- Fields used from sidecar JSON:
- `photoTakenTime.timestamp` or `creationTime.timestamp` to place items by date
- Schema shape:
- Directory tree of symlinks organized by date
- Writer:
- `scripts/build_view_by_date_takeout.py` (parses timestamps, creates symlinks).

## Parsed-but-Unused Fields / TODOs

- No sidecar fields are parsed and then unused within the same script.
- Sidecar fields are not used for dedupe decisions.

## Code References

- `scripts/build_view_by_date_takeout.py`
- `parse_google_ts_seconds` reads `photoTakenTime.timestamp` and `creationTime.timestamp`.
- Main loop loads `*.supplemental-metadata.json` via `json.load` and uses timestamps to build the by-date view.

- `scripts/write_sidecars_from_takeout.py`
- `extract_google_photo_ids` reads `url` and recursively searches `photoId`, `mediaId`, `googlePhotoId`, `id`.
- `extract_people` reads `people[].name`.
- `extract_geo` reads `geoData.latitude`, `geoData.longitude`, `geoData.altitude`, `geoData.latitudeSpan`, `geoData.longitudeSpan`.
- Writes per-canonical sidecar JSON to `CANON/*.shafferography.json`.

- `scripts/build_run_plan.py`
- Dedupe hash is computed from media bytes via SHA-256 and does not use sidecar JSON.
